#!/bin/bash
set -e

# Install Docker
apt update -y
apt install -y docker.io python3
systemctl enable docker
systemctl start docker

# Docker cgroup fix
cat <<EOF > /etc/docker/daemon.json
{
  "exec-opts": ["native.cgroupdriver=systemd"]
}
EOF
systemctl restart docker

# Disable Swap
swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab

# Kernel settings for Kubernetes
cat <<EOF | tee /etc/modules-load.d/containerd.conf
overlay
br_netfilter
EOF

modprobe overlay
modprobe br_netfilter

cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF

sysctl --system

# Install Kubernetes
apt install -y apt-transport-https curl ca-certificates
curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key \
| gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' \
> /etc/apt/sources.list.d/kubernetes.list

apt update -y
apt install -y kubelet kubeadm kubectl
systemctl enable kubelet

# Initialize cluster
kubeadm init --pod-network-cidr=192.168.0.0/16

sleep 30

# Configure kubectl
mkdir -p /home/ubuntu/.kube
cp /etc/kubernetes/admin.conf /home/ubuntu/.kube/config
chown ubuntu:ubuntu /home/ubuntu/.kube/config

# Install Calico
su - ubuntu -c "kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.27.2/manifests/calico.yaml"

# Generate dynamic join command
kubeadm token create --print-join-command > /home/ubuntu/join.sh
chmod +x /home/ubuntu/join.sh

# Share join command
cd /home/ubuntu
nohup python3 -m http.server 8080 > server.log 2>&1 &