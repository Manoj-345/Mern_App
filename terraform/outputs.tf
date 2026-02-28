output "master_public_ip" {
  value = aws_instance.master.public_ip
}

output "master_private_ip" {
  value = aws_instance.master.private_ip
}

output "asg_name" {
  value = aws_autoscaling_group.worker_asg.name
}

output "sns_topic_arn" {
  value = aws_sns_topic.alerts.arn
}