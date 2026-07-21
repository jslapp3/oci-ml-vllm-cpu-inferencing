variable "tenancy_ocid" {
  description = "OCI tenancy OCID. Leave null when using OCI CLI/profile environment auth."
  type        = string
  default     = null
}

variable "user_ocid" {
  description = "OCI user OCID. Leave null when using OCI CLI/profile environment auth."
  type        = string
  default     = null
}

variable "fingerprint" {
  description = "API key fingerprint. Leave null when using OCI CLI/profile environment auth."
  type        = string
  default     = null
}

variable "private_key_path" {
  description = "Path to OCI API private key. Leave null when using OCI CLI/profile environment auth."
  type        = string
  default     = null
}

variable "region" {
  description = "OCI region, for example us-ashburn-1."
  type        = string
}

variable "compartment_ocid" {
  description = "Compartment OCID for all resources."
  type        = string
}

variable "availability_domain" {
  description = "Availability domain name, for example Uocm:US-ASHBURN-AD-1."
  type        = string
}

variable "project_name" {
  description = "Name prefix for resources."
  type        = string
  default     = "oci-vllm-ml-inference"
}

variable "vcn_cidr" {
  description = "VCN CIDR block."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public orchestrator subnet."
  type        = string
  default     = "10.0.0.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR block for the private vLLM subnet."
  type        = string
  default     = "10.0.1.0/24"
}

variable "admin_cidr_blocks" {
  description = "CIDR blocks allowed to SSH to the public orchestrator VM."
  type        = list(string)
  default     = []
}

variable "public_api_cidr_blocks" {
  description = "CIDR blocks allowed to call the public orchestrator API on TCP/8080."
  type        = list(string)
  default     = []
}

variable "ssh_public_key_path" {
  description = "Path to the public SSH key to inject into both instances."
  type        = string
}

variable "orchestrator_shape" {
  description = "Shape for the public orchestrator and Chronos VM."
  type        = string
  default     = "VM.Standard.E6.Ax.Flex"
}

variable "orchestrator_ocpus" {
  description = "OCPUs for the orchestrator VM."
  type        = number
  default     = 2
}

variable "orchestrator_memory_gbs" {
  description = "Memory for the orchestrator VM."
  type        = number
  default     = 16
}

variable "orchestrator_private_ip" {
  description = "Fixed private IP for the orchestrator VM in the public subnet."
  type        = string
  default     = "10.0.0.71"
}

variable "vllm_shape" {
  description = "Shape for the private CPU vLLM VM."
  type        = string
  default     = "VM.Standard.E6.Ax.Flex"
}

variable "vllm_ocpus" {
  description = "OCPUs for the private CPU vLLM VM."
  type        = number
  default     = 16
}

variable "vllm_memory_gbs" {
  description = "Memory for the private CPU vLLM VM."
  type        = number
  default     = 128
}

variable "vllm_private_ip" {
  description = "Fixed private IP for the vLLM VM in the private subnet."
  type        = string
  default     = "10.0.1.98"
}

variable "orchestrator_boot_volume_size_gbs" {
  description = "Boot volume size for the orchestrator VM."
  type        = number
  default     = 100
}

variable "orchestrator_python_version" {
  description = "Python major/minor version installed for Chronos and the orchestrator."
  type        = string
  default     = "3.11"
}

variable "vllm_boot_volume_size_gbs" {
  description = "Boot volume size for the vLLM VM."
  type        = number
  default     = 200
}

variable "vllm_python_version" {
  description = "Exact managed Python version installed for vLLM."
  type        = string
  default     = "3.12.13"
}

variable "uv_version" {
  description = "Pinned uv installer version used on the vLLM host."
  type        = string
  default     = "0.11.28"
}

variable "vllm_version" {
  description = "Pinned vLLM release installed from the matching CPU wheel index."
  type        = string
  default     = "0.24.0"
}

variable "image_id" {
  description = "Optional Oracle Linux image OCID. If null, Terraform selects a recent Oracle Linux image for the orchestrator shape."
  type        = string
  default     = null
}

variable "oracle_linux_version" {
  description = "Oracle Linux version used by image lookup when image_id is null."
  type        = string
  default     = "9"
}

variable "app_repo_url" {
  description = "Git URL for this application repo. Leave empty to provision infrastructure without installing the app."
  type        = string
  default     = ""
}

variable "app_repo_ref" {
  description = "Git ref to check out after cloning the app repo."
  type        = string
  default     = "main"
}

variable "chronos_load_public_model" {
  description = "Whether the orchestrator VM should load the public Chronos model."
  type        = bool
  default     = true
}

variable "chronos_force_fallback" {
  description = "Whether Chronos should force fallback mode."
  type        = bool
  default     = false
}

variable "vllm_model" {
  description = "Model served by the private vLLM CPU VM."
  type        = string
  default     = "Qwen/Qwen3-0.6B"
}

variable "vllm_api_key" {
  description = "Bearer token for the private vLLM endpoint."
  type        = string
  sensitive   = true
}

variable "hf_token" {
  description = "Optional Hugging Face token for model downloads."
  type        = string
  default     = ""
  sensitive   = true
}

variable "vllm_timeout_seconds" {
  description = "Orchestrator timeout when calling CPU vLLM."
  type        = number
  default     = 60
}

variable "vllm_cpu_kvcache_space_gbs" {
  description = "GiB reserved for vLLM CPU KV cache."
  type        = number
  default     = 16
}
