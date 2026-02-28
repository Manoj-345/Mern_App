variable "ami" {
  description = "Ubuntu 24.04 LTS x86"
  default     = "ami-0b6c6ebed2801a5cb"
}

variable "instance_type" {
  default = "t2.medium"
}

variable "key_name" {
  description = "Your AWS key pair name"
}