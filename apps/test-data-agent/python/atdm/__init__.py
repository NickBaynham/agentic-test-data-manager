"""Agentic Test Data Manager — client library and CLI.

Usage:
    # CLI:
    atdm request active_member_clean
    atdm reset <run_id> --token <token>
    atdm audit <run_id>

    # Python:
    from atdm.client import AtdmClient
    client = AtdmClient()
    response = client.request_scenario("active_member_clean")

    # pytest:
    from atdm.pytest import atdm_scenario

    @atdm_scenario("active_member_clean")
    def test_member(atdm_data):
        assert atdm_data["data"]["member_id"].startswith("m-")
"""

from atdm.client import AtdmClient, AtdmClientError

__all__ = ["AtdmClient", "AtdmClientError"]
