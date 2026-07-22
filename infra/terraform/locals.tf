locals {
  name_prefix = var.project_name

  common_tags = {
    project = var.project_name
    managed = "terraform"
  }

  orchestrator_image_id = coalesce(
    var.orchestrator_image_id,
    var.image_id,
    data.oci_core_images.orchestrator_oracle_linux.images[0].id,
  )
  vllm_image_id = coalesce(
    var.vllm_image_id,
    var.image_id,
    data.oci_core_images.vllm_oracle_linux.images[0].id,
  )
}

data "oci_core_images" "orchestrator_oracle_linux" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Oracle Linux"
  operating_system_version = var.oracle_linux_version
  shape                    = var.orchestrator_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

data "oci_core_images" "vllm_oracle_linux" {
  compartment_id           = var.compartment_ocid
  operating_system         = "Oracle Linux"
  operating_system_version = var.oracle_linux_version
  shape                    = var.vllm_shape
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}
