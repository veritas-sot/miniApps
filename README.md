__Veritas-SOT miniapps__

To use the golden config plugin, use this GraphQL query:

query ($device_id: ID!)
{
  device(id: $device_id) {
    id
    name
    hostname: name
    primary_ip4 {
      id
      ip_version
      address
      description
      mask_length
      dns_name
      interfaces {
        id
        name
      }
    }
    role {
      id
      name
    }
    device_type {
      id
      model
    }
    platform {
      id
      name
      manufacturer {
        name
      }
    }
    tags {
      id
      name
      content_types {
        id
        app_label
        model
      }
    }
    tenant {
      id
      name
      tenant_group {
        name
      }
    }
    rack {
      id
      name
    }
    location {
      id
      name
    }
    status {
      id
      name
    }
    asset_tag
    config_context
    _custom_field_data
    _custom_field_data
    custom_field_data: _custom_field_data
    position
    serial
    interfaces {
      id
      name
      description
      enabled
      mac_address
      type
      mode
      status {
        id
        name
      }
      ip_addresses {
        address
        status {
          id
          name
        }
        role {
          id
        }
        tags {
          id
          name
        }
        parent {
          id
          network
          prefix
          prefix_length
          namespace {
            id
            name
          }
        }
      }
      connected_circuit_termination {
        circuit {
          cid
          commit_rate
          provider {
            name
          }
        }
      }
      tagged_vlans {
        id
        name
        vid
      }
      untagged_vlan {
        id
        name
        vid
      }
      cable {
        id
        termination_a_type
        status {
          name
        }
        color
      }
      tags {
        id
        name
        content_types {
          id
          app_label
          model
        }
      }
      lag {
        id
        name
        enabled
      }
      member_interfaces {
        id
        name
      }
    }
  }
}