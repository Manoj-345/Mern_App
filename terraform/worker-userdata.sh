#!/bin/bash
set -e

MASTER_IP="${master_ip}"

# Install Docker
apt update -y
apt install -y docker.io
systemctl enable docker
systemctl start docker

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

# Wait for master join command dynamically
until curl -s http://${MASTER_IP}:8080/join.sh -o /tmp/join.sh; do
  echo "Waiting for master..."
  sleep 10
done

bash /tmp/join.sh