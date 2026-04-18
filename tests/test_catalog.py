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
        "foreignKeys": [{"table": "mydb.public.customers", "column": "customer_id"}],
    }
    result = OpenMetadataClient._fk_name(col)
    assert result == "mydb.public.customers.customer_id"


def test_fk_name_returns_none_for_regular_column():
    col = {"name": "status", "dataType": "VARCHAR", "description": "Status"}
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


# --- _domain_name helper ---


def test_domain_name_from_dict_name_key():
    assert OpenMetadataClient._domain_name({"name": "Customer", "id": "abc"}) == "Customer"


def test_domain_name_from_dict_fqn_fallback():
    assert OpenMetadataClient._domain_name({"fullyQualifiedName": "Revenue"}) == "Revenue"


def test_domain_name_from_string():
    assert OpenMetadataClient._domain_name("Sales") == "Sales"


def test_domain_name_none_input():
    assert OpenMetadataClient._domain_name(None) is None


def test_domain_name_empty_dict():
    assert OpenMetadataClient._domain_name({}) is None


# --- TableSummary with domain field (new OM response shape) ---


def test_parse_table_summary_with_domain_object():
    """list_tables now reads business_domain from the 'domain' field, not tags."""
    domain_field = {"name": "Customer", "id": "uuid-1", "type": "domain"}
    summary = TableSummary(
        name="mydb.public.cust",
        description="Customers",
        business_domain=OpenMetadataClient._domain_name(domain_field),
    )
    assert summary.business_domain == "Customer"


def test_parse_table_summary_without_domain():
    summary = TableSummary(
        name="mydb.public.orders",
        description="Orders",
        business_domain=OpenMetadataClient._domain_name(None),
    )
    assert summary.business_domain is None
