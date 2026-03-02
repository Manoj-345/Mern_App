#!/bin/bash
set -e

MASTER_IP="${master_ip}"

apt update -y
apt install -y docker.io curl apt-transport-https ca-certificates gpg

systemctl enable docker
systemctl start docker

cat <<EOF > /etc/docker/daemon.json
{
  "exec-opts": ["native.cgroupdriver=systemd"]
}
EOF
systemctl restart docker

swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab

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

mkdir -p /etc/apt/keyrings

curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key \
| gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' \
> /etc/apt/sources.list.d/kubernetes.list

apt update -y
apt install -y kubelet kubeadm kubectl
systemctl enable kubelet

until curl -s http://${master_ip}:8080/join.sh -o /tmp/join.sh; do
  echo "Waiting for master..."
  sleep 10
done

bash /tmp/join.sh