from .v1_baseline import V1_SYSTEM, V1_USER_TEMPLATE
from .v2_schema_enforced import V2_SYSTEM, V2_USER_TEMPLATE
from .v3_few_shot import V3_SYSTEM, V3_USER_TEMPLATE

PROMPT_VERSIONS = {
    "v1": (V1_SYSTEM, V1_USER_TEMPLATE),
    "v2": (V2_SYSTEM, V2_USER_TEMPLATE),
    "v3": (V3_SYSTEM, V3_USER_TEMPLATE),
}
