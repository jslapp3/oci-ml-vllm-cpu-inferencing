resource "oci_core_instance" "orchestrator" {
  availability_domain = var.availability_domain
  compartment_id      = var.compartment_ocid
  display_name        = "${local.name_prefix}-orchestrator"
  shape               = var.orchestrator_shape
  freeform_tags       = local.common_tags

  shape_config {
    ocpus         = var.orchestrator_ocpus
    memory_in_gbs = var.orchestrator_memory_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.public.id
    assign_public_ip = true
    hostname_label   = "orchestrator"
    private_ip       = var.orchestrator_private_ip
    nsg_ids          = [oci_core_network_security_group.orchestrator.id]
  }

  source_details {
    source_type             = "image"
    source_id               = local.selected_image_id
    boot_volume_size_in_gbs = var.boot_volume_size_gbs
  }

  metadata = {
    ssh_authorized_keys = file(var.ssh_public_key_path)
    user_data = base64encode(templatefile("${path.module}/cloud-init/orchestrator.yaml.tftpl", {
      app_repo_url              = var.app_repo_url
      app_repo_ref              = var.app_repo_ref
      chronos_load_public_model = var.chronos_load_public_model
      chronos_force_fallback    = var.chronos_force_fallback
      vllm_base_url             = "http://${var.vllm_private_ip}:8000/v1"
      vllm_model                = var.vllm_model
      vllm_api_key              = var.vllm_api_key
      vllm_timeout_seconds      = var.vllm_timeout_seconds
    }))
  }
}

resource "oci_core_instance" "vllm" {
  availability_domain = var.availability_domain
  compartment_id      = var.compartment_ocid
  display_name        = "${local.name_prefix}-vllm-cpu"
  shape               = var.vllm_shape
  freeform_tags       = local.common_tags

  shape_config {
    ocpus         = var.vllm_ocpus
    memory_in_gbs = var.vllm_memory_gbs
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.private.id
    assign_public_ip = false
    hostname_label   = "vllm"
    private_ip       = var.vllm_private_ip
    nsg_ids          = [oci_core_network_security_group.vllm.id]
  }

  source_details {
    source_type             = "image"
    source_id               = local.selected_image_id
    boot_volume_size_in_gbs = var.boot_volume_size_gbs
  }

  metadata = {
    ssh_authorized_keys = file(var.ssh_public_key_path)
    user_data = base64encode(templatefile("${path.module}/cloud-init/vllm-cpu.yaml.tftpl", {
      orchestrator_private_cidr = "${var.orchestrator_private_ip}/32"
      vllm_model                = var.vllm_model
      vllm_api_key              = var.vllm_api_key
      hf_token                  = var.hf_token
      vllm_cpu_kvcache_space    = var.vllm_cpu_kvcache_space_gbs
    }))
  }
}
