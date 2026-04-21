import os
import time
import requests
import boto3
from kubernetes import client, config


# ENV VARIABLES

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")

CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", 70))
MEMORY_THRESHOLD = float(os.getenv("MEMORY_THRESHOLD", 75))
MAX_REPLICAS = int(os.getenv("MAX_REPLICAS", 5))

DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME", "quickchat-backend")
NAMESPACE = os.getenv("NAMESPACE", "default")

ASG_NAME = os.getenv("ASG_NAME")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK")
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN")

CHECK_INTERVAL = 60
COOLDOWN = 300

last_scaled_time = 0


# INIT K8S + AWS CLIENTS

try:
    config.load_incluster_config()
    print("✅ Using in-cluster Kubernetes config")
except:
    config.load_kube_config()
    print("✅ Using local kubeconfig")

apps_v1 = client.AppsV1Api()

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
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=5
        )
        data = r.json()

        if data["status"] == "success" and data["data"]["result"]:
            return float(data["data"]["result"][0]["value"][1])

    except Exception as e:
        print("❌ Prometheus error:", e)

    return None


def get_metrics():
    return query_prometheus(CPU_QUERY), query_prometheus(MEMORY_QUERY)


# ALERTING


def send_alert(msg):
    print(f"📣 ALERT: {msg}")

    if SLACK_WEBHOOK:
        try:
            requests.post(SLACK_WEBHOOK, json={"text": msg}, timeout=5)
        except:
            pass

    if SNS_TOPIC_ARN:
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=msg,
                Subject="🚨 AIOps Alert"
            )
        except:
            pass


# CLOUDWATCH


def push_metrics(cpu, memory):
    try:
        cloudwatch.put_metric_data(
            Namespace="AIOps",
            MetricData=[
                {"MetricName": "CPU", "Value": cpu, "Unit": "Percent"},
                {"MetricName": "Memory", "Value": memory, "Unit": "Percent"},
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
        print(f"🔎 Current replicas: {replicas}")

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
        return

    try:
        response = autoscaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=[ASG_NAME]
        )

        groups = response["AutoScalingGroups"]
        if not groups:
            return

        current = groups[0]["DesiredCapacity"]

        autoscaling.set_desired_capacity(
            AutoScalingGroupName=ASG_NAME,
            DesiredCapacity=current + 1,
            HonorCooldown=False
        )

        print(f"🚀 ASG scaled to {current + 1}")

    except Exception as e:
        print("❌ ASG error:", e)


# AIOPS LOGIC 


def run_aiops():
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

    # decision engine
    if cpu > CPU_THRESHOLD or memory > MEMORY_THRESHOLD:

        send_alert(
            f"🚨 HIGH LOAD DETECTED | CPU: {cpu:.2f}% | MEM: {memory:.2f}%"
        )

        scaled = scale_kubernetes()

        if not scaled:
            print("⚠️ Kubernetes failed → scaling ASG")
            scale_asg()

        last_scaled_time = time.time()

    else:
        print("✅ System healthy - no scaling needed")

    print("🏁 ===== AIOPS FINISHED =====\n")


# MAIN LOOP (AIOPS ENGINE)

if __name__ == "__main__":
    print("🔥 AIOps Engine Started")

    while True:
        try:
            run_aiops()
        except Exception as e:
            print("❌ Unexpected error:", e)

        time.sleep(CHECK_INTERVAL)