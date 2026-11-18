# Lab Fixture Checklist: one export that covers the configuration surface

**Goal:** build one ClearPass **lab** configuration that uses every feature likely to
change the XML export's structure, then export it once. The resulting file becomes
`tests/fixtures/LabKitchenSink.xml` and anchors parser support for features we have
never seen in a real export.

**Why this list:** a ClearPass DB backup (`tipsdb`) has one table per kind of
configuration, even when it's empty. The items below are the tables with **0 rows**
in our lab backup (`reference-files/tipsdb.pgdump`), plus areas our current fixtures
don't cover. Table names are given as evidence; the matching XML element names are
what this exercise will tell us.

> Template and menu names vary between ClearPass versions. Use whatever the
> **Add Enforcement Profile → Template** list shows on your version, and tick
> every variant you see, not just the ones named here.

**Rules for the lab config**
- Lab appliance only. Use dummy names, IPs, secrets and AD/LDAP details.
- One service per feature area is enough. Keep names descriptive, e.g. `kit-dur-cx`.
- Wire each profile into an enforcement policy **used by a service**. The export
  only includes objects reachable from the exported services.
- Before exporting, upload the file to the app: any amber "does not interpret"
  warning means the catch-all found something new, which is useful on its own.

---

## 1. Enforcement profiles (highest value)
Each profile type is a separate XML element and needs its own parser support.

| ✓ | Profile type (template) | Configure at least | DB evidence |
|---|---|---|---|
| ☐ | **Aruba Downloadable Role (all DUR variants in the dropdown)** | role with **ACLs/policies, VLAN, QoS/policer**; one per plugin (CX, AOS-8/controller, AOS-S switch if offered) | `dur_role_config_details` (0), `aos_acl_*`, `aos_netdestination*`, `aos_profile_config*`, `hpe_role_config` (0), `role_config` (0) |
| ☐ | Aruba RADIUS Enforcement | Aruba-User-Role, Aruba-Named-User-Vlan | `tips_enf_profile_radius_params` |
| ☐ | VLAN / Filter-ID based enforcement | Tunnel-Private-Group-Id, Filter-Id | covered partly (synthetic fixture) |
| ☐ | Cisco Downloadable ACL Enforcement | multi-line dACL | radius params |
| ☐ | Cisco RADIUS / Web-Auth Enforcement | cisco-av-pair, url-redirect | radius params |
| ☐ | RADIUS CoA (several **templates**: Aruba, Cisco, HPE, Juniper…) | one bounce/disconnect + one reauth/change-role | `tips_radius_coa_templates` (37 built-in) |
| ☐ | **TACACS+ Based Enforcement** with **command authorization** | services (shell + one other), priv-lvl, **permit/deny command list with arguments** | `tips_tacacs_cmd` (0), `tips_tacacs_cmd_args` (0), `tips_enf_profile_tacacs_allowed_service` |
| ☐ | **SNMP Based Enforcement** | VLAN change / port bounce | `tips_enf_profile_snmp*` (0) |
| ☐ | **Agent / Agent Script Enforcement** (OnGuard) | bounce + notification message | `tips_enf_profile_agent*` (0) |
| ☐ | **CLI Based** and **HTTP Based Enforcement** | one command / one HTTP action | (not in table list: check how they export) |
| ☐ | Generic Application Enforcement | 2+ params | `tips_enf_profile_app*` |
| ☐ | Post-auth: **ClearPass Entity Update** | endpoint attribute + status update | `tips_enf_profile_post_auth_params` |
| ☐ | Post-auth: **Session Restrictions** | bandwidth / session-time limits | post_auth type `SessionRestriction` |
| ☐ | Post-auth: **Session Notification** | target server | post_auth type `SessionNotify` |
| ☐ | Any profile restricted to **NAD groups** | 2 NAD groups | `*_nad_group` tables |

## 2. Services and service options

| ✓ | Item | Notes |
|---|---|---|
| ☐ | A service from **each service template** in the list (23 built-in) | e.g. 802.1X wired/wireless, MAC auth, MPSK/IPSK, Aruba Device Access (TACACS), guest web-auth, OAuth2 API access, SAML SP, eduroam/RADIUS proxy |
| ☐ | **Posture Compliance** enabled (+ posture policy, default posture token, remediation) | `tips_service_posture*` |
| ☐ | **Audit End-hosts** enabled (Nmap/Nessus audit server) | `tips_service_audit_details` |
| ☐ | **Profile Endpoints** enabled (+ CoA profile on category change) | `tips_service_coa` |
| ☐ | **Accounting Proxy** targets | `tips_service_acct_proxy_servers` |
| ☐ | RADIUS proxy with **multiple targets** and **reply-attribute filtering** | `tips_service_filter_proxy_reply_params` |
| ☐ | **MFA** on a service (if your version offers it) | `tips_service_mfa_policy` |
| ☐ | **Authorization** sources (several) separate from auth sources | `tips_service_autz_source` |
| ☐ | Monitor mode ON; Use cached results ON; strip-username rules | flags (already parsed) |
| ☐ | A **disabled** service and a `------Divider------` service | picker behaviour |

## 3. Rules and conditions

| ✓ | Item | Notes |
|---|---|---|
| ☐ | Role mapping and enforcement policies in **evaluate-all** and **first-applicable** | both algorithms |
| ☐ | Conditions using many **namespaces**: Tips:Role, Tips:Posture, Endpoint, Authorization:<AD/LDAP/SQL>, Connection, Date (day/time ranges), Device (NAD group / location), Host, Certificate, Guest | normalizer coverage |
| ☐ | Many **operators**: BELONGS_TO_GROUP, NOT_BELONGS_TO_GROUP, MATCHES_ALL/ANY, regex, IN_RANGE / date ranges, EXISTS/NOT_EXISTS, CONTAINS/NOT_CONTAINS, BEGINS_WITH | an unknown operator anywhere currently **fails the whole upload (HTTP 422)** |
| ☐ | A rule with **multiple profiles**, and a rule whose profiles mix RADIUS + post-auth | action / end-node logic |
| ☐ | Role mapping that uses **Role:** conditions from a previous match (nested roles) | |

## 4. Supporting objects (lower priority; usually shown by name only)
☐ Static host lists ☐ Device groups ☐ Auth source with backup servers and attribute filters ☐ Endpoint tags / tag dictionaries ☐ Local users with a role

---

## After exporting
1. Upload the file in the app and note every amber "does not interpret" warning.
2. Save it as `tests/fixtures/LabKitchenSink.xml` (check that no real secrets or names are in it).
3. Optionally take a new DB backup of the same lab. Rows in the tables above
   let us map DB ↔ XML for the future `.pgdump` input.
4. Prioritise parser support by what appears in real customer exports. The
   coverage report (planned) will measure that without sharing configurations.
