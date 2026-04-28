
import import_declare_test

from splunktaucclib.rest_handler.endpoint import (
    field,
    validator,
    RestModel,
    SingleModel,
)
from splunktaucclib.rest_handler import admin_external, util
from splunktaucclib.rest_handler.admin_external import AdminExternalHandler
import logging


util.remove_http_proxy_env_vars()


special_fields = [
    field.RestField(
        'name',
        required=True,
        encrypted=False,
        default=None,
        validator=validator.AllOf(
            validator.Pattern(
                regex=r"""^[a-zA-Z]\w*$""", 
            ), 
            validator.String(
                max_len=50, 
                min_len=1, 
            )
        )
    )
]

fields = [
    field.RestField(
        'cribl_url',
        required=True,
        encrypted=False,
        default=None,
        validator=validator.AllOf(
            validator.Pattern(
                regex=r"""^[a-zA-Z0-9][a-zA-Z0-9._-]*[a-zA-Z0-9]$""", 
            ), 
            validator.String(
                max_len=200, 
                min_len=5, 
            )
        )
    ), 
    field.RestField(
        'cribl_instance',
        required=True,
        encrypted=False,
        default='cribl.cloud',
        validator=None
    ), 
    field.RestField(
        'cribl_client_id',
        required=True,
        encrypted=False,
        default=None,
        validator=validator.String(
            max_len=200, 
            min_len=1, 
        )
    ), 
    field.RestField(
        'cribl_client_secret',
        required=True,
        encrypted=True,
        default=None,
        validator=validator.String(
            max_len=500, 
            min_len=1, 
        )
    ), 
    field.RestField(
        'is_default',
        required=False,
        encrypted=False,
        default=False,
        validator=None
    )
]
model = RestModel(fields, name=None, special_fields=special_fields)


endpoint = SingleModel(
    'criblsearch_account',
    model,
    config_name='account',
    need_reload=False,
)


if __name__ == '__main__':
    logging.getLogger().addHandler(logging.NullHandler())
    admin_external.handle(
        endpoint,
        handler=AdminExternalHandler,
    )
