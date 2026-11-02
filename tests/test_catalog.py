import pytest

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


def test_table_foreign_keys_simple():
    raw = {
        "name": "orders",
        "tableConstraints": [
            {
                "constraintType": "FOREIGN_KEY",
                "columns": ["customer_id"],
                "referredColumns": ["svc.db.public.customers.customer_id"],
            }
        ],
    }
    assert OpenMetadataClient._table_foreign_keys(raw) == [
        "orders(customer_id) -> customers(customer_id)"
    ]


def test_table_foreign_keys_composite():
    raw = {
        "name": "ops",
        "tableConstraints": [
            {
                "constraintType": "FOREIGN_KEY",
                "columns": ["agent", "entity", "origin"],
                "referredColumns": [
                    "svc.db.s.agents.agent_code",
                    "svc.db.s.agents.entity",
                    "svc.db.s.agents.origin",
                ],
            }
        ],
    }
    assert OpenMetadataClient._table_foreign_keys(raw) == [
        "ops(agent, entity, origin) -> agents(agent_code, entity, origin)"
    ]


def test_table_foreign_keys_ignores_other_and_malformed_constraints():
    raw = {
        "name": "t",
        "tableConstraints": [
            {"constraintType": "UNIQUE", "columns": ["a"]},
            {"constraintType": "FOREIGN_KEY", "columns": ["a", "b"], "referredColumns": ["x.y.z"]},
            {"constraintType": "FOREIGN_KEY", "columns": ["a"], "referredColumns": ["nodots"]},
        ],
    }
    assert OpenMetadataClient._table_foreign_keys(raw) == []
    assert OpenMetadataClient._table_foreign_keys({"name": "t"}) == []


# --- _first_domain_name (OM 2.x `domains` list, singular `domain` fallback) ---


def test_first_domain_name_from_domains_list():
    raw = {"domains": [{"name": "Claims", "id": "a"}, {"name": "Other", "id": "b"}]}
    assert OpenMetadataClient._first_domain_name(raw) == "Claims"


def test_first_domain_name_falls_back_to_singular_domain():
    assert OpenMetadataClient._first_domain_name({"domain": {"name": "Customer"}}) == "Customer"


def test_first_domain_name_prefers_domains_over_domain():
    raw = {"domains": [{"name": "New"}], "domain": {"name": "Old"}}
    assert OpenMetadataClient._first_domain_name(raw) == "New"


def test_first_domain_name_missing_or_empty():
    assert OpenMetadataClient._first_domain_name({}) is None
    assert OpenMetadataClient._first_domain_name({"domains": []}) is None


# --- business rules / extension merge ---


class _FakeResponse:
    def __init__(self, payload):  # noqa: ANN001
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self):  # noqa: ANN201
        return self._payload


@pytest.mark.asyncio
async def test_merge_table_extension_keeps_existing_properties(monkeypatch):
    client = OpenMetadataClient("http://om", api_token="t")
    patches: list = []

    async def fake_get(url):  # noqa: ANN001, ANN202
        return _FakeResponse({"extension": {"commonQueries": "- q1"}})

    async def fake_patch(fqn, payload):  # noqa: ANN001, ANN202
        patches.append((fqn, payload))

    monkeypatch.setattr(client, "_get", fake_get)
    monkeypatch.setattr(client, "patch_table", fake_patch)
    await client.merge_table_extension("svc.db.s.t", {"businessRules": "- latest version"})
    assert patches == [
        (
            "svc.db.s.t",
            [
                {
                    "op": "add",
                    "path": "/extension",
                    "value": {"commonQueries": "- q1", "businessRules": "- latest version"},
                }
            ],
        )
    ]


@pytest.mark.asyncio
async def test_merge_table_extension_without_existing_extension(monkeypatch):
    client = OpenMetadataClient("http://om", api_token="t")
    patches: list = []

    async def fake_get(url):  # noqa: ANN001, ANN202
        return _FakeResponse({})

    async def fake_patch(fqn, payload):  # noqa: ANN001, ANN202
        patches.append(payload)

    monkeypatch.setattr(client, "_get", fake_get)
    monkeypatch.setattr(client, "patch_table", fake_patch)
    await client.merge_table_extension("t", {"businessRules": "r"})
    assert patches[0][0]["value"] == {"businessRules": "r"}


@pytest.mark.asyncio
async def test_get_table_reads_business_rules(monkeypatch):
    client = OpenMetadataClient("http://om", api_token="t")

    async def fake_get(url):  # noqa: ANN001, ANN202
        return _FakeResponse(
            {
                "fullyQualifiedName": "svc.db.s.t",
                "columns": [],
                "extension": {"businessRules": "- use the latest version"},
            }
        )

    monkeypatch.setattr(client, "_get", fake_get)
    table = await client.get_table("svc.db.s.t")
    assert table.business_rules == "- use the latest version"
