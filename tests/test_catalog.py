from artoo.catalog.openmetadata import OpenMetadataClient
from artoo.models import TableSummary


def test_headers_with_token():
    client = OpenMetadataClient(base_url="http://localhost:8585", api_token="test-token")
    headers = client._headers()
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Content-Type"] == "application/json"


def test_headers_without_token():
    client = OpenMetadataClient(base_url="http://localhost:8585", api_token=None)
    headers = client._headers()
    assert "Authorization" not in headers
    assert headers["Content-Type"] == "application/json"


def test_fk_name_detects_foreign_key():
    col = {
        "name": "cust_id",
        "dataType": "INT",
        "constraint": "ForeignKey",
        "foreignKeys": [{"table": "hotel_demo.public.cust", "column": "cust_id"}],
    }
    result = OpenMetadataClient._fk_name(col)
    assert result == "hotel_demo.public.cust.cust_id"


def test_fk_name_returns_none_for_regular_column():
    col = {"name": "bk_status", "dataType": "VARCHAR", "description": "Status"}
    assert OpenMetadataClient._fk_name(col) is None


def test_fk_name_returns_none_for_none_constraint():
    col = {"name": "x", "dataType": "INT", "constraint": None}
    assert OpenMetadataClient._fk_name(col) is None


def test_fk_name_returns_none_for_empty_fk():
    col = {
        "name": "cust_id",
        "dataType": "INT",
        "constraint": "ForeignKey",
        "foreignKeys": [],
    }
    assert OpenMetadataClient._fk_name(col) is None


def test_parse_table_summary_with_tag():
    item = {
        "fullyQualifiedName": "hotel_demo.public.cust",
        "name": "cust",
        "description": "Customers",
        "tags": [{"tagFQN": "Business.customer"}],
    }
    tags = item.get("tags") or [{}]
    summary = TableSummary(
        name=item.get("fullyQualifiedName", item.get("name")),
        description=item.get("description"),
        business_domain=tags[0].get("tagFQN") if tags and tags[0] else None,
    )
    assert summary.name == "hotel_demo.public.cust"
    assert summary.description == "Customers"
    assert summary.business_domain == "Business.customer"


def test_parse_table_summary_without_tags():
    item = {
        "fullyQualifiedName": "hotel_demo.public.bkng",
        "name": "bkng",
        "description": "Bookings",
        "tags": None,
    }
    tags = item.get("tags") or [{}]
    summary = TableSummary(
        name=item.get("fullyQualifiedName", item.get("name")),
        description=item.get("description"),
        business_domain=tags[0].get("tagFQN") if tags and tags[0] else None,
    )
    assert summary.business_domain is None


def test_list_tables_url_encoding_params():
    client = OpenMetadataClient(base_url="http://om:8585", api_token=None)
    base = f"{client.base_url}/api/v1/tables?fields=description,usageSummary&limit=100"
    assert "om:8585" in base
    assert "limit=100" in base
