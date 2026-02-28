import os
import requests
import time
import boto3
from kubernetes import client, config

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-server:9090")
CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", 0.7))
MAX_REPLICAS = int(os.getenv("MAX_REPLICAS", 5))

DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME", "quickchat-backend")
NAMESPACE = os.getenv("NAMESPACE", "default")

ASG_NAME = os.getenv("ASG_NAME", "quickchat-worker-asg")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK")
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN")

config.load_incluster_config()

apps_v1 = client.AppsV1Api()
core_v1 = client.CoreV1Api()

autoscaling = boto3.client("autoscaling", region_name=AWS_REGION)
cloudwatch = boto3.client("cloudwatch", region_name=AWS_REGION)
sns = boto3.client("sns", region_name=AWS_REGION)

def get_cpu_usage():
    try:
        query = 'sum(rate(container_cpu_usage_seconds_total{namespace="default"}[1m]))'
        response = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": query},
            timeout=5
        )
        result = response.json()

        if result["status"] == "success" and result["data"]["result"]:
            return float(result["data"]["result"][0]["value"][1])
    except Exception as e:
        print("Prometheus error:", e)
    return 0

def scale_kubernetes():
    try:
        deployment = apps_v1.read_namespaced_deployment(
            DEPLOYMENT_NAME, NAMESPACE
        )
        replicas = deployment.spec.replicas

        if replicas < MAX_REPLICAS:
            body = {"spec": {"replicas": replicas + 1}}
            apps_v1.patch_namespaced_deployment(
                DEPLOYMENT_NAME, NAMESPACE, body
            )
            print(f"Kubernetes scaled to {replicas + 1}")
            return True

        print("Max replicas reached")
        return False
    except Exception as e:
        print("Kubernetes scaling error:", e)
        return False

def restart_failed_pods():
    try:
        pods = core_v1.list_namespaced_pod(NAMESPACE)
        for pod in pods.items:
            if pod.metadata.labels.get("app") == "backend":
                for container_status in pod.status.container_statuses or []:
                    if container_status.restart_count > 3:
                        print("Restarting pod:", pod.metadata.name)
                        core_v1.delete_namespaced_pod(
                            pod.metadata.name, NAMESPACE
                        )
    except Exception as e:
        print("Pod restart error:", e)

def scale_asg():
    try:
        response = autoscaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=[ASG_NAME]
        )
        groups = response.get("AutoScalingGroups", [])
        if not groups:
            print("ASG not found")
            return

        asg = groups[0]
        current_capacity = asg["DesiredCapacity"]

        autoscaling.set_desired_capacity(
            AutoScalingGroupName=ASG_NAME,
            DesiredCapacity=current_capacity + 1,
            HonorCooldown=False
        )
        print("EC2 ASG scaled")
    except Exception as e:
        print("ASG scaling error:", e)

def send_slack(message):
    if SLACK_WEBHOOK:
        try:
            requests.post(SLACK_WEBHOOK, json={"text": message}, timeout=5)
        except Exception as e:
            print("Slack error:", e)

def send_sns(message):
    if SNS_TOPIC_ARN:
        try:
            sns.publish(
                TopicArn=SNS_TOPIC_ARN,
                Message=message,
                Subject="QuickChat AIOps Alert"
            )
        except Exception as e:
            print("SNS error:", e)

def push_metric(cpu):
    try:
        cloudwatch.put_metric_data(
            Namespace="QuickChat/AIOps",
            MetricData=[{
                "MetricName": "CPUUsage",
                "Value": cpu,
                "Unit": "Percent"
            }]
        )
    except Exception as e:
        print("CloudWatch error:", e)

def main():
    print("AIOps Started...")
    while True:
        try:
            cpu = get_cpu_usage()
            print("CPU:", cpu)

            push_metric(cpu)
            restart_failed_pods()

            if cpu > CPU_THRESHOLD:
                message = f"🚨 High CPU detected: {cpu}"

                scaled = scale_kubernetes()
                if not scaled:
                    scale_asg()

                send_slack(message)
                send_sns(message)

        except Exception as e:
            print("Main loop error:", e)

        time.sleep(60)

if __name__ == "__main__":
    main()