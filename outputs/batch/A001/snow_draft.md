# ServiceNow Draft: A001

Alarm A001 ICMP Unreachable; BGP neighbor down on rtr-site001-core (site001)

## Validation Results
- target (10.1.1.1): FAIL loss=100% rtt=Nonems
- sw-site001-edge01 (10.1.2.11): PASS loss=0% rtt=12ms
- sw-site001-edge02 (10.1.2.12): PASS loss=0% rtt=11ms

## Attachments
- site001.txt
- prior_incidents.json
- config.txt

## Blast Radius
- Scope: Device only (isolated)
- Why: Target unreachable while all discovered neighbors responded successfully.

## Suggested Next Steps
- Check device power/CPU, mgmt reachability, console access.
- Verify BGP session state, peer reachability, recent route changes/maintenance.
