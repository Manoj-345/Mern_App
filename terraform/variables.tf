variable "instance_type" {
  default = "t3.small"
}

variable "key_name" {
  description = "EC2 key pair"
  default     = "devops"
}