# Workload Registration

## Workload Information Collection

The following workload information will be collected during workload onboarding. You can onboard your workload to IDR in two phases. You can start by onboarding just your workload without any alarm(s), and then you can add alarms. For more information about how IDR helps you with incidents for a workload onboarded into each phase, check out our user guide: https://docs.aws.amazon.com/IDR/latest/userguide/idr-gs-onboard-workload.html#workload-onboarding 

- **Workload Name**
  - Make this unique. It can be anything you choose. This name appears in the support cases that IDR creates when we detect an incident.

- **Regions**
  - Set the regions in which your AWS resources are used. This helps IDR map AWS service events to your application.

You will then have the option to review and edit this information.

## Tag-based Resource Discovery

The CLI performs automated resource discovery using tags. The CLI will prompt you for tag information during resource discovery.This tag information is used to identify the specific AWS resources to be onboarded. There are two ways to provide single/multiple tags. Note that if you want to specify specifically which ARNs IDR should monitor, without using tags, [you can accomplish this in unattended mode](../unattended-mode.md)

```
Step 4/7: Discover Eligible Resources

Resource Discovery
──────────────────

How would you like to specify tags?:
  1. Single tag (key and value separately)
  2. Multiple tags (key1=value1,key2=value1|value2)
→ Enter your choice (1-2) :
```

**Option 1:** The CLI will prompt for tag key and tag value separately. You can enter only 1 key-value pair

**Option 2:** The CLI will ask for a tag key-value expression. This allows you to enter multiple key-value pairs at once

Examples:
```
# Filter resources with two tags
key1=value1, key2=value2

# Filter resources with either value
key1=value1|value2
```

## AWS Resource Selection

After providing tags for resource discovery, the CLI automatically discovers resources that match the tag. Then, the tool takes you to the ‘Total resource view’ with a prompt to select whether you want to onboard all discovered resources or want to customize selection. This is how you specify which resources IDR should monitor. 

```
Resource Selection
──────────────────

───────────────────
Total resource view
───────────────────

Discovered 29 eligible resources in 2 regions.

NOTE: Resources not eligible for monitoring like IAM roles, security 
groups, and subnets are excluded.

What would you like to do?:
  1 → Select all 29 resources in 1 regions and proceed to submitting your workload onboarding information
  2 → Review and customize resource selection
  3 → Go back to change the tag filter
→ Enter number (1-3): 1
```

When you choose to select all discovered resources (option 1), the CLI will do a ‘Final confirmation’ prompt with a breakdown of resource selection per region:

```
──────────────────
Final confirmation
──────────────────

Selection summary
────────────────────────────────
us-east-1: 24 selected of 24
us-west-2: 4 selected of 4
global: 1 selected of 1
────────────────────────────────
TOTAL: 29 selected of 29

What would you like to do?::
1 → Confirm and continue with 29 of 29 selected
2 → Edit selection
→ Enter number (1-2): 2
```

You can either confirm the selection with option 1 and proceed to submitting onboarding case, or edit the selection.

When you choose to edit the selection (option 2) in the ‘Final confirmation’ view or choose to review and customize selection (option 2) in the ‘Total resource view’ view, CLI presents the ‘Regional view’ of the discovered resources. The interface should look similar to the following:

```
Resource Selection
──────────────────

─────────────
Regional view
─────────────

You ve chosen to review and customize resource selection.

What would you like to do?:
1 → Select all 29 resources in 2 regions and proceed to submitting your workload onboarding information
2 → Deselect all 29 resources
3 → Review resources in all (2) regions and customize selection (Currently 0 selected of 29)
4 → Review global resources (Currently 0 selected  of 1)
5 → Review us-east-1 resources (Currently 0 of 24 selected)
6 → Review us-west-2 resources (Currently 0 of 4 selected)
→ Enter number (1-6): 6

```

You can choose to select all discovered resources and proceed to submitting your workload onboarding case (option 1), review resources in all regions (option 3) or review resources per region (options 4-6). Note, that global resources have a separate regional category. Global resources are non-region specific resources like S3 or CloudFront.

After selecting the review option (3-6), you will be presented with a ‘Resource group view’ for the selected region. This view shows discovered resource types, resource count for each type and number of currently selected resources:

```
Resource Selection
──────────────────

────────────────────────────────────────────────────────────────────────
Regional view > Resource group view in us-west-2 region
────────────────────────────────────────────────────────────────────────

To change region, use 'Accept and go back' option

Resource count per type in us-west-2 region:
  apigateway: 1, selected 0
  elasticloadbalancing:loadbalancer: 1, selected 0
  lambda:function: 2, selected 0
Currently selected: 0 of 4 resources

What would you like to do?:
1 → Select all 4 resources and go back to "Regional view"
2 → Deselect all 4 resources
3 → Accept current resource selection (0 of 4 resources selected) and go back to "Regional view"
4 → Review individual resources and customize selection
→ Enter number (1-4): 4 
```

From there, you can use ‘Select all’ option to select all resources and go back to ‘Regional view’. You can use option 3 to accept current selection and go back to ‘Regional view’, but since there is no currently selected resources, you may want to review resource details with option 4:

```
Resource Selection
──────────────────

──────────────────────────────────────────────────────────────────────────────────────────────────────
Regional view > Resource group view in us-west-2 region > Individual resource view in us-west-2 region
──────────────────────────────────────────────────────────────────────────────────────────────────────

To change region, use 'Accept and go back' option

Resource list in us-west-2 region:
Item details:
1: apigateway: IDR-CLI-Test-Test-API - not selected
    Region: us-west-2 | Resource ID: xxxxxxxxxx
2: elasticloadbalancing:loadbalancer: IDR-CLI-Test-Test-ALB - not selected
    Region: us-west-2 | Resource ID: yyyyyyyyyy
3: lambda:function: IDR-CLI-Test-EC2ManagementFunction - not selected
    Region: us-west-2
4: lambda:function: IDR-CLI-Test-Test-Function-2 - not selected
    Region: us-west-2 | Resource ID: idr-cli-test-function-2

Currently selected: 0 of 4 items


What would you like to do?:
  1-4 → Mark resource as selected by number
  5 → Deselect all
  6 → Accept current resource selection (0 selected of 29) and go back to "Resource group view in us-west-2 region"
→ Enter number (1-6): 4 
```

Here you can use number 1-4 to select each individual resource. As you manage the selection, the resource selection status will change to ‘selected’ and the number of selected items will increment. Select ‘Accept current resource selection’ (option 6) when done and go back to the previous level - ‘Resource group view’. 

To complete the selection, you need to go up to the ‘Regional view’. The menu will have an option to ‘Accept current selection and proceed to onboarding’:

```
Resource Selection
──────────────────

─────────────
Regional view
─────────────

You ve chosen to review and customize resource selection.

What would you like to do?:
1 → Select all 29 resources in 2 regions and proceed to submitting your workload onboarding information
2 → Deselect all 29 resources
3 → Accept current selection (Currently 4 selected of 29) and proceed to onboarding
4 → Review resources in all (2) regions and customize selection (Currently 4 selected of 29)
5 → Review global resources (Currently 0 selected  of 1)
6 → Review us-east-1 resources (Currently 0 of 24 selected)
7 → Review us-west-2 resources (Currently 4 of 4 selected)
→ Enter number (1-7): 3
```

Once you select option 3, CLI will present the ‘Final confirmation’ resource selection prompt and then will proceed to submitting your workload onboarding information.

## Support Case Creation

All you need to do to register your workload with IDR is provide a name, the regions, and the associated resources. Once this is complete, the CLI helps you create a Support Case so IDR systems can complete onboarding your application. 
The CLI creates a new support case on your behalf for workload information ingestion. There will be a confirmation message:

```
→ Are you ready to submit the workload with the above information and create a support case? [y/n] (y): y

✅ A support case has been created
```

If you answer n to the confirm message, the CLI will terminate, and you can execute  awsidr register-workload again when you are ready to create an IDR onboarding support case. 

If you already have a workload registered, then you can use awsidr create-alarms. Instead of creating a new support case, the CLI updates an existing support case with a new attachment if a corresponding workload support case already exists.


## See Also

- [Main README](../../README.md)
- [CloudWatch Alarm Creation](cloudwatch-alarms.md)
- [Alarm Ingestion](alarm-ingestion.md)
- [Workflows](../workflows.md)
- [Unattended Mode](../unattended-mode.md)
- [IAM Policies](../iam-policies.md)
- [Appendix](../appendix.md)
