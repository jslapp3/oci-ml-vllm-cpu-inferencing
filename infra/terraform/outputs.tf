output "orchestrator_public_ip" {
  description = "Public IP address for the orchestrator/Chronos VM."
  value       = oci_core_instance.orchestrator.public_ip
}

output "orchestrator_private_ip" {
  description = "Private IP address for the orchestrator/Chronos VM."
  value       = oci_core_instance.orchestrator.private_ip
}

output "vllm_private_ip" {
  description = "Private IP address for the vLLM CPU VM."
  value       = oci_core_instance.vllm.private_ip
}

output "ssh_orchestrator" {
  description = "SSH command for the public orchestrator VM."
  value       = "ssh opc@${oci_core_instance.orchestrator.public_ip}"
}

output "ssh_vllm_via_orchestrator" {
  description = "SSH command for the private vLLM VM through the orchestrator jump host."
  value       = "ssh -J opc@${oci_core_instance.orchestrator.public_ip} opc@${oci_core_instance.vllm.private_ip}"
}
