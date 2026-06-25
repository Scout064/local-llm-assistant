from __future__ import annotations

import asyncio
import structlog
from proxmoxer import ProxmoxAPI

try:
    from proxmoxer.core import ResourceException as _ProxmoxResourceError
except ImportError:
    _ProxmoxResourceError = Exception

log = structlog.get_logger()


class ProxmoxService:
    def __init__(self, host: str, user: str, token_name: str, token_value: str, verify_ssl: bool = False):
        self.host = host
        self.user = user
        self.token_name = token_name
        self.token_value = token_value
        self.verify_ssl = verify_ssl
        self._proxmox: ProxmoxAPI | None = None

    @property
    def proxmox(self) -> ProxmoxAPI:
        if self._proxmox is None:
            self._proxmox = ProxmoxAPI(
                self.host,
                user=self.user,
                token_name=self.token_name,
                token_value=self.token_value,
                verify_ssl=self.verify_ssl,
            )
        return self._proxmox

    async def health_check(self) -> bool:
        try:
            return bool(await asyncio.to_thread(self.proxmox.nodes.get))
        except Exception:
            return False

    async def list_vms(self) -> list[dict]:
        def _list():
            vms = []
            nodes = self.proxmox.nodes.get()
            for node in nodes:
                node_vms = self.proxmox.nodes(node["node"]).qemu.get()
                for vm in node_vms:
                    vm["node"] = node["node"]
                    vms.append(vm)
                node_lxc = self.proxmox.nodes(node["node"]).lxc.get()
                for ct in node_lxc:
                    ct["node"] = node["node"]
                    ct["type"] = "lxc"
                    vms.append(ct)
            return vms
        return await asyncio.to_thread(_list)

    async def get_vm_status(self, vmid: int) -> dict:
        def _status():
            nodes = self.proxmox.nodes.get()
            for node_info in nodes:
                node = node_info["node"]
                try:
                    status = self.proxmox.nodes(node).qemu(vmid).status.current.get()
                    status["node"] = node
                    return status
                except _ProxmoxResourceError as e:
                    if "not found" in str(e).lower():
                        continue
                    log.error("proxmox_api_error", vmid=vmid, error=str(e))
                    return {"error": f"Proxmox API error: {e}"}
                except Exception as e:
                    log.error("proxmox_unexpected_error", vmid=vmid, error=str(e))
                    return {"error": f"Unexpected error: {e}"}
            return {"error": f"VM {vmid} not found on any node"}
        return await asyncio.to_thread(_status)

    async def start_vm(self, vmid: int) -> str:
        def _start():
            nodes = self.proxmox.nodes.get()
            for node_info in nodes:
                node = node_info["node"]
                try:
                    self.proxmox.nodes(node).qemu(vmid).status.start.post()
                    return f"VM {vmid} start initiated on {node}"
                except _ProxmoxResourceError as e:
                    if "not found" in str(e).lower():
                        continue
                    return f"Error: Proxmox API error: {e}"
                except Exception as e:
                    return f"Error: Unexpected error: {e}"
            return f"Error: VM {vmid} not found"
        return await asyncio.to_thread(_start)

    async def stop_vm(self, vmid: int) -> str:
        def _stop():
            nodes = self.proxmox.nodes.get()
            for node_info in nodes:
                node = node_info["node"]
                try:
                    self.proxmox.nodes(node).qemu(vmid).status.stop.post()
                    return f"VM {vmid} stop initiated on {node}"
                except _ProxmoxResourceError as e:
                    if "not found" in str(e).lower():
                        continue
                    return f"Error: Proxmox API error: {e}"
                except Exception as e:
                    return f"Error: Unexpected error: {e}"
            return f"Error: VM {vmid} not found"
        return await asyncio.to_thread(_stop)