import os
import requests
import boto3
import time
from kubernetes import client, config


# ENV VARIABLES

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", 70))  # percentage
MEMORY_THRESHOLD = float(os.getenv("MEMORY_THRESHOLD", 75))

MAX_REPLICAS = int(os.getenv("MAX_REPLICAS", 5))

DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME", "quickchat-backend")
NAMESPACE = os.getenv("NAMESPACE", "default")

ASG_NAME = os.getenv("ASG_NAME")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK")
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN")

COOLDOWN = 300
CHECK_INTERVAL = 60  # seconds

last_scaled_time = 0


# INIT CLIENTS

# Kubernetes config (works both inside & outside cluster)
try:
    config.load_incluster_config()
    print("✅ Using in-cluster Kubernetes config")
except:
    config.load_kube_config()
    print("✅ Using local kubeconfig")

apps_v1 = client.AppsV1Api()

# AWS clients
autoscaling = boto3.client("autoscaling", region_name=AWS_REGION)
cloudwatch = boto3.client("cloudwatch", region_name=AWS_REGION)
sns = boto3.client("sns", region_name=AWS_REGION)


# PROMETHEUS QUERIES


CPU_QUERY = """
100 - (avg(irate(node_cpu_seconds_total{mode="idle"}[1m])) * 100)
"""

MEMORY_QUERY = """
100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))
"""


# METRICS


def query_prometheus(query):
    try:
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=5
        )
        result = response.json()

        if result["status"] == "success" and result["data"]["result"]:
            return float(result["data"]["result"][0]["value"][1])

    except Exception as e:
        print("❌ Prometheus error:", e)

    return None


def get_metrics():
    cpu = query_prometheus(CPU_QUERY)
    memory = query_prometheus(MEMORY_QUERY)
    return cpu, memory


# ALERTS


def send_alert(message):
    print(f"📣 ALERT: {message}")

    # Slack
    if SLACK_WEBHOOK:
        try:
            requests.post(SLACK_WEBHOOK, json={"text": message}, timeout=5)
        except Exception as e:
            print("❌ Slack error:", e)

    # SNS
    if SNS_TOPIC_ARN:
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=message,
                Subject="🚨 AIOps Alert"
            )
        except Exception as e:
            print("❌ SNS error:", e)


# CLOUDWATCH

def push_metrics(cpu, memory):
    try:
        cloudwatch.put_metric_data(
            Namespace="QuickChat/AIOps",
            MetricData=[
                {"MetricName": "CPUUsage", "Value": cpu, "Unit": "Percent"},
                {"MetricName": "MemoryUsage", "Value": memory, "Unit": "Percent"}
            ]
        )
    except Exception as e:
        print("❌ CloudWatch error:", e)


# KUBERNETES SCALING


def scale_kubernetes():
    try:
        scale = apps_v1.read_namespaced_deployment_scale(
            name=DEPLOYMENT_NAME,
            namespace=NAMESPACE
        )

        replicas = scale.spec.replicas

        if replicas >= MAX_REPLICAS:
            print("⚠️ Max replicas reached")
            return False

        new_replicas = replicas + 1

        apps_v1.patch_namespaced_deployment_scale(
            name=DEPLOYMENT_NAME,
            namespace=NAMESPACE,
            body={"spec": {"replicas": new_replicas}}
        )

        print(f"🚀 Kubernetes scaled to {new_replicas}")
        return True

    except Exception as e:
        print("❌ Kubernetes scaling error:", e)
        return False


# ASG SCALING


def scale_asg():
    if not ASG_NAME:
        print("⚠️ No ASG configured")
        return

    try:
        response = autoscaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=[ASG_NAME]
        )

        groups = response.get("AutoScalingGroups", [])
        if not groups:
            print("⚠️ ASG not found")
            return

        asg = groups[0]
        current = asg["DesiredCapacity"]

        autoscaling.set_desired_capacity(
            AutoScalingGroupName=ASG_NAME,
            DesiredCapacity=current + 1,
            HonorCooldown=False
        )

        print(f"🚀 ASG scaled to {current + 1}")

    except Exception as e:
        print("❌ ASG error:", e)


# MAIN LOGIC


def main():
    global last_scaled_time

    print("\n🚀 ===== AIOPS ENGINE RUNNING =====")

    cpu, memory = get_metrics()

    if cpu is None or memory is None:
        print("❌ Failed to fetch metrics")
        return

    print(f"📊 CPU: {cpu:.2f}% | Memory: {memory:.2f}%")

    push_metrics(cpu, memory)

    # cooldown check
    if time.time() - last_scaled_time < COOLDOWN:
        print("⏳ Cooldown active - skipping scaling")
        return

    # stress detection
    if cpu > CPU_THRESHOLD or memory > MEMORY_THRESHOLD:

        message = f"🚨 NODE STRESS DETECTED | CPU: {cpu:.2f}% | MEM: {memory:.2f}%"
        send_alert(message)

        # Kubernetes scaling
        scaled = scale_kubernetes()

        # fallback to ASG
        if not scaled:
            print("⚠️ Kubernetes scaling failed → scaling ASG")
            scale_asg()

        last_scaled_time = time.time()

    else:
        print("✅ System healthy")

    print("🏁 ===== CYCLE COMPLETE =====\n")


# RUN LOOP

if __name__ == "__main__":
    print("🔥 Starting AIOps Engine...")

    while True:
        try:
            main()
        except Exception as e:
            print("❌ Unexpected error:", e)

        time.sleep(CHECK_INTERVAL)