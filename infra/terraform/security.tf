resource "oci_core_security_list" "nsg_only" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${local.name_prefix}-nsg-only-sl"
  freeform_tags  = local.common_tags
}

resource "oci_core_network_security_group" "orchestrator" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${local.name_prefix}-orchestrator-nsg"
  freeform_tags  = local.common_tags
}

resource "oci_core_network_security_group" "vllm" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${local.name_prefix}-vllm-nsg"
  freeform_tags  = local.common_tags
}

resource "oci_core_network_security_group_security_rule" "orchestrator_egress_all" {
  network_security_group_id = oci_core_network_security_group.orchestrator.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  description               = "Allow orchestrator outbound traffic."
}

resource "oci_core_network_security_group_security_rule" "vllm_egress_all" {
  network_security_group_id = oci_core_network_security_group.vllm.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  description               = "Allow vLLM outbound traffic through NAT."
}

resource "oci_core_network_security_group_security_rule" "orchestrator_ssh" {
  for_each = toset(var.admin_cidr_blocks)

  network_security_group_id = oci_core_network_security_group.orchestrator.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  description               = "SSH to orchestrator from admin CIDR."

  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_network_security_group_security_rule" "orchestrator_api" {
  for_each = toset(var.public_api_cidr_blocks)

  network_security_group_id = oci_core_network_security_group.orchestrator.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = each.value
  source_type               = "CIDR_BLOCK"
  description               = "Public orchestrator API on TCP/8080."

  tcp_options {
    destination_port_range {
      min = 8080
      max = 8080
    }
  }
}

resource "oci_core_network_security_group_security_rule" "vllm_ssh_from_orchestrator" {
  network_security_group_id = oci_core_network_security_group.vllm.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "${var.orchestrator_private_ip}/32"
  source_type               = "CIDR_BLOCK"
  description               = "SSH to private vLLM VM through orchestrator jump host."

  tcp_options {
    destination_port_range {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_network_security_group_security_rule" "vllm_api_from_orchestrator" {
  network_security_group_id = oci_core_network_security_group.vllm.id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = "${var.orchestrator_private_ip}/32"
  source_type               = "CIDR_BLOCK"
  description               = "Private OpenAI-compatible vLLM endpoint from orchestrator only."

  tcp_options {
    destination_port_range {
      min = 8000
      max = 8000
    }
  }
}
