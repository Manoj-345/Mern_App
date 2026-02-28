import os

PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus-server:9090")

CPU_THRESHOLD = float(os.getenv("CPU_THRESHOLD", 0.7))
MAX_REPLICAS = int(os.getenv("MAX_REPLICAS", 5))

DEPLOYMENT_NAME = os.getenv("DEPLOYMENT_NAME", "quickchat-backend")
NAMESPACE = "default"

ASG_NAME = os.getenv("ASG_NAME", "quickchat-worker-asg")

SLACK_WEBHOOK = os.getenv("SLACK_WEBHOOK")
SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN")

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")