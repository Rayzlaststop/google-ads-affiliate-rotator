import os
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf import field_mask_pb2


def load_client() -> GoogleAdsClient:
    os.environ.setdefault("GOOGLE_ADS_USE_PROTO_PLUS", "True")
    return GoogleAdsClient.load_from_env()


def update_campaign_suffix(client: GoogleAdsClient, customer_id: str, campaign_id: str, suffix: str) -> None:
    campaign_service = client.get_service("CampaignService")

    operation = client.get_type("CampaignOperation")
    campaign = operation.update
    campaign.resource_name = campaign_service.campaign_path(customer_id, campaign_id)
    campaign.final_url_suffix = suffix

    client.copy_from(
        operation.update_mask,
        field_mask_pb2.FieldMask(paths=["final_url_suffix"]),
    )

    try:
        response = campaign_service.mutate_campaigns(
            customer_id=customer_id,
            operations=[operation],
        )
        print(f"  Campaign {campaign_id} updated: {response.results[0].resource_name}")
    except GoogleAdsException as ex:
        print(f"  ERROR updating campaign {campaign_id}: {ex.error.code().name}", file=sys.stderr)
        for error in ex.failure.errors:
            print(f"    {error.message}", file=sys.stderr)
        raise
