#!/bin/bash
set -e



# Install dependencies

apt update -y
apt install -y containerd curl apt-transport-https ca-certificates gpg netcat-openbsd


# Configure containerd

mkdir -p /etc/containerd
containerd config default | tee /etc/containerd/config.toml

sed -i 's/SystemdCgroup = false/SystemdCgroup = true/' /etc/containerd/config.toml

systemctl restart containerd
systemctl enable containerd


# Disable swap

swapoff -a
sed -i '/ swap / s/^/#/' /etc/fstab


# Kernel settings

modprobe overlay
modprobe br_netfilter

cat <<EOF | tee /etc/sysctl.d/k8s.conf
net.bridge.bridge-nf-call-iptables = 1
net.ipv4.ip_forward = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF

sysctl --system


# Install Kubernetes

mkdir -p /etc/apt/keyrings

curl -fsSL https://pkgs.k8s.io/core:/stable:/v1.29/deb/Release.key \
| gpg --dearmor -o /etc/apt/keyrings/kubernetes-apt-keyring.gpg

echo 'deb [signed-by=/etc/apt/keyrings/kubernetes-apt-keyring.gpg] https://pkgs.k8s.io/core:/stable:/v1.29/deb/ /' \
> /etc/apt/sources.list.d/kubernetes.list

apt update -y
apt install -y kubelet kubeadm kubectl
systemctl enable kubelet


# Wait for master API

echo "Waiting for master..."

until nc -z ${master_ip} 6443; do
  sleep 10
done


# Join cluster (IMPORTANT 🔥)

kubeadm join ${master_ip}:6443 \
  --token y0mjcu.j833e3mwir4mkjic \
  --discovery-token-ca-cert-hash sha256:e5dbf6fe6885af4cb0f8d0a84db921b988722b2aced8dbd481c8af79a1f71175
echo "Worker joined successfully!"