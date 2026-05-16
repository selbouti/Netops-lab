import requests
import yaml
import time

api_url = "http://localhost:3080/v2"

# ─────────────────────────────────────────
# FONCTIONS DE BASE
# ─────────────────────────────────────────

def create_project(name):
    response = requests.get(api_url + "/projects")
    response.raise_for_status()
    projects = response.json()
    
    for p in projects:
        if p["name"] == name:
            print(f"Projet existant trouvé — suppression...")
            requests.delete(api_url + f"/projects/{p['project_id']}")
            print(f"Projet supprimé")
            break
    url = api_url + "/projects"
    data = {"name": name}
    response = requests.post(url, json=data)
    response.raise_for_status()
    project = response.json()
    print(f"Projet créé : {project['name']} — ID : {project['project_id']}")
    return project
def open_project(project_id):
    url = api_url + f"/projects/{project_id}/open"
    response = requests.post(url)
    response.raise_for_status()
    print(f"Projet ouvert : {project_id}")

def get_templates():
    url = api_url + "/templates"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def find_template(templates, name=None, template_type=None):
    for t in templates:
        if name and t["name"] == name:
            return t["template_id"]
        if template_type and t["template_type"] == template_type:
            return t["template_id"]
    raise ValueError(f"Template introuvable : name={name} type={template_type}")


def create_node_from_template(name, project_id, template_id, x=0, y=0):
    url = api_url + f"/projects/{project_id}/templates/{template_id}"
    data = {
        "name": name,
        "x": x,
        "y": y,
        "compute_id": "local"
    }
    response = requests.post(url, json=data)
    response.raise_for_status()
    node = response.json()
    print(f"Nœud créé : {node['name']} — ID : {node['node_id']}")
    return node


def create_link(project_id, node1_id, node2_id,
                adapter1=0, port1=0, adapter2=0, port2=0):
    url = api_url + f"/projects/{project_id}/links"
    data = {
        "nodes": [
            {
                "node_id": node1_id,
                "adapter_number": adapter1,
                "port_number": port1
            },
            {
                "node_id": node2_id,
                "adapter_number": adapter2,
                "port_number": port2
            }
        ]
    }
    response = requests.post(url, json=data)
    print(f"Status: {response.status_code}")
    print(f"Réponse: {response.text}")

    response.raise_for_status()
    link = response.json()
    print(f"Lien créé : {node1_id} ←→ {node2_id}")
    return link


def start_all_nodes(project_id):
    url = api_url + f"/projects/{project_id}/nodes/start"
    response = requests.post(url)
    response.raise_for_status()
    print("Tous les noeuds démarrés")


def generate_inventory(routers, switches, filepath="ansible/inventory/hosts.yml"):
    inventory = {
        "all": {
            "children": {
                "routers": {
                    "hosts": {
                        r["name"]: {
                            "ansible_host": f"192.168.1.{i+1}",
                            "ansible_network_os": "ios",
                            "ansible_user": "admin",
                            "ansible_password": "admin",
                            "ansible_connection": "network_cli"
                        }
                        for i, r in enumerate(routers)
                    }
                },
                "switches": {
                    "hosts": {
                        s["name"]: {
                            "ansible_host": f"192.168.1.{i+10}",
                            "ansible_network_os": "ios",
                            "ansible_user": "admin",
                            "ansible_password": "admin",
                            "ansible_connection": "network_cli"
                        }
                        for i, s in enumerate(switches)
                    }
                },
                "cloud_vms": {
                    "hosts": {
                        "VM-Proxmox": {"ansible_host": "10.10.0.2"},
                        "VM-ESXi":    {"ansible_host": "10.10.0.3"},
                        "VM-Ceph":    {"ansible_host": "10.10.0.4"}
                    },
                    "vars": {
                        "ansible_user": "root",
                        "ansible_connection": "ssh",
                        "ansible_ssh_private_key_file": "~/.ssh/id_rsa"
                    }
                }
            }
        }
    }
    with open(filepath, "w") as f:
        yaml.dump(inventory, f, default_flow_style=False)
    print(f"Inventaire Ansible généré : {filepath}")


# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

def main():

    # 1. Créer le projet
    project = create_project("enterprise-3tier")
    pid = project["project_id"]
    open_project(pid)
    # 2. Récupérer les templates
    templates = get_templates()
    router_tid = find_template(templates, name="c3600")
    switch_tid = find_template(templates, template_type="ethernet_switch")
    cloud_tid  = find_template(templates, template_type="cloud")

    # 3. Noeud Cloud — porte de sortie vers WireGuard / Internet
    cloud_gw = create_node_from_template(
        "Cloud-GW", pid, cloud_tid, x=300, y=-300
    )

    # 4. Tier 1 — Core routers
    r1 = create_node_from_template("R1-Core", pid, router_tid, x=150, y=-100)
    r2 = create_node_from_template("R2-Core", pid, router_tid, x=450, y=-100)

    # 5. Tier 2 — Backbone switches
    sw_bb1 = create_node_from_template("SW-BB1", pid, switch_tid, x=150, y=100)
    sw_bb2 = create_node_from_template("SW-BB2", pid, switch_tid, x=450, y=100)

    # 6. Tier 3 — Access switches
    sw_acc1 = create_node_from_template("SW-Acc1", pid, switch_tid, x=50,  y=300)
    sw_acc2 = create_node_from_template("SW-Acc2", pid, switch_tid, x=200, y=300)
    sw_acc3 = create_node_from_template("SW-Acc3", pid, switch_tid, x=380, y=300)
    sw_acc4 = create_node_from_template("SW-Acc4", pid, switch_tid, x=530, y=300)
# 7. Liens Cloud-GW → Routeurs
    create_link(pid, cloud_gw["node_id"], r1["node_id"], port1=0, adapter2=0, port2=0)
    create_link(pid, cloud_gw["node_id"], r2["node_id"], port1=1, adapter2=0, port2=0)

    # 8. Liens Core → Backbone (adapter change, pas port)
    create_link(pid, r1["node_id"], sw_bb1["node_id"], adapter1=1, port1=0, port2=0)
    create_link(pid, r1["node_id"], sw_bb2["node_id"], adapter1=2, port1=0, port2=0)
    create_link(pid, r2["node_id"], sw_bb1["node_id"], adapter1=1, port1=0, port2=1)
    create_link(pid, r2["node_id"], sw_bb2["node_id"], adapter1=2, port1=0, port2=1)

    # 9. Liens Backbone → Access
    create_link(pid, sw_bb1["node_id"], sw_acc1["node_id"], port1=2, port2=0)
    create_link(pid, sw_bb1["node_id"], sw_acc2["node_id"], port1=3, port2=0)
    create_link(pid, sw_bb2["node_id"], sw_acc3["node_id"], port1=2, port2=0)
    create_link(pid, sw_bb2["node_id"], sw_acc4["node_id"], port1=3, port2=0)

    # 10. Démarrer tous les noeuds
    start_all_nodes(pid)

    # 11. Attendre le boot des routeurs
    print("Attente boot 30 secondes...")
    time.sleep(30)

    # 12. Générer l inventaire Ansible
    routers  = [r1, r2]
    switches = [sw_bb1, sw_bb2, sw_acc1, sw_acc2, sw_acc3, sw_acc4]
    generate_inventory(routers, switches)

    print("\n✓ Topologie enterprise-3tier déployée avec succès !")
    print(f"  Projet ID   : {pid}")
    print(f"  Cloud-GW    : pointe vers wg0 (WireGuard)")
    print(f"  VM-Proxmox  : 10.10.0.2")
    print(f"  VM-ESXi     : 10.10.0.3")
    print(f"  VM-Ceph     : 10.10.0.4")
    print(f"  Inventaire  : ansible/inventory/hosts.yml")


if __name__ == "__main__":
    main()