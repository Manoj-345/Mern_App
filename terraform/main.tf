
# DEFAULT VPC

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# S3 BUCKET FOR TERRAFORM STATE

resource "aws_s3_bucket" "tf_state" {
  bucket = "quickchat-terraform-state"

  tags = {
    Name = "QuickChat Terraform State"
  }
}

resource "aws_s3_bucket_versioning" "tf_state_versioning" {
  bucket = aws_s3_bucket.tf_state.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tf_state_encryption" {
  bucket = aws_s3_bucket.tf_state.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# SECURITY GROUP

resource "aws_security_group" "k8s_sg" {
  name   = "quickchat-k8s-sg"
  vpc_id = data.aws_vpc.default.id

  ingress {
    description = "Allow All Traffic (Lab Only)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# SNS TOPIC

resource "aws_sns_topic" "alerts" {
  name = "quickchat-alerts"
}

# IAM ROLE FOR WORKER NODES

resource "aws_iam_role" "worker_role" {
  name = "quickchat-worker-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "autoscaling" {
  role       = aws_iam_role.worker_role.name
  policy_arn = "arn:aws:iam::aws:policy/AutoScalingFullAccess"
}

resource "aws_iam_role_policy_attachment" "sns" {
  role       = aws_iam_role.worker_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSNSFullAccess"
}

resource "aws_iam_role_policy_attachment" "cloudwatch" {
  role       = aws_iam_role.worker_role.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchFullAccess"
}

resource "aws_iam_instance_profile" "worker_profile" {
  name = "quickchat-worker-profile"
  role = aws_iam_role.worker_role.name
}

# MASTER NODE

resource "aws_instance" "master" {
  ami                    = var.ami
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.k8s_sg.id]
  key_name               = var.key_name

  user_data = file("${path.module}/master-userdata.sh")

  tags = {
    Name = "quickchat-master"
  }
}

# WORKER LAUNCH TEMPLATE

resource "aws_launch_template" "worker_template" {
  name_prefix   = "quickchat-worker"
  image_id      = var.ami
  instance_type = var.instance_type
  key_name      = var.key_name

  iam_instance_profile {
    name = aws_iam_instance_profile.worker_profile.name
  }

  vpc_security_group_ids = [aws_security_group.k8s_sg.id]

  user_data = base64encode(
    templatefile("${path.module}/worker-userdata.sh", {
      master_ip = aws_instance.master.private_ip
    })
  )
}

# AUTOSCALING GROUP

resource "aws_autoscaling_group" "worker_asg" {
  name                = "quickchat-worker-asg"
  desired_capacity    = 1
  min_size            = 1
  max_size            = 3
  vpc_zone_identifier = data.aws_subnets.default.ids

  launch_template {
    id      = aws_launch_template.worker_template.id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "quickchat-worker"
    propagate_at_launch = true
  }
}

# CLOUDWATCH ALARM

resource "aws_cloudwatch_metric_alarm" "cpu_alarm" {
  alarm_name          = "quickchat-high-cpu"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Average"
  threshold           = 70

  dimensions = {
    AutoScalingGroupName = aws_autoscaling_group.worker_asg.name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

# OUTPUTS

output "master_public_ip" {
  value = aws_instance.master.public_ip
}

output "sns_topic_arn" {
  value = aws_sns_topic.alerts.arn
}