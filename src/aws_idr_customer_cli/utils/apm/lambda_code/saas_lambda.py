import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EventBusName = os.environ["EnvEventBusName"]
# Get incident path from environment variable for flexible updates
INCIDENT_PATH = os.environ.get("INCIDENT_PATH", 'event["detail"]["workflowName"]')


def lambda_handler(event: dict, context: object) -> None:
    logger.info(event)
    # Set the event["detail"]["incident-detection-response-identifier"] value
    # to the name of your alert that is coming from your APM. Each APM is
    # different and each unique alert will have a different name.
    # Use environment variable for incident path for flexible console updates

    try:
        # Safely evaluate the incident path from environment variable
        incident_identifier = eval(INCIDENT_PATH)
        event["detail"]["incident-detection-response-identifier"] = incident_identifier
    except Exception as e:
        logger.error(f"Error evaluating incident path '{INCIDENT_PATH}': {e}")
        # Fallback to default path
        event["detail"]["incident-detection-response-identifier"] = event["detail"][
            "workflowName"
        ]

    logger.info(f"Received payload: {json.dumps(event, indent=2)}")

    client = boto3.client("events")
    response = client.put_events(
        Entries=[
            {
                "Detail": json.dumps(event["detail"], indent=2),
                # Do not modify. This DetailType value is required.
                "DetailType": "ams.monitoring/generic-apm",
                # Do not modify. This Source value is required.
                "Source": "GenericAPMEvent",
                # Do not modify. This variable is set at the top of this code
                # as a global variable. Change the variable value for your
                # eventbus name at the top of this code.
                "EventBusName": EventBusName,
            }
        ]
    )
    logger.info(f"Final payload: {response['Entries']}")
