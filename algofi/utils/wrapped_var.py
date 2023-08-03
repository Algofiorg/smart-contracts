"""A wrapper for global and local variables."""
from pyteal import *

GLOBAL_VAR = "GLOBAL_VAR"
GLOBAL_EX_VAR = "GLOBAL_EX_VAR"
LOCAL_VAR = "LOCAL_VAR"
LOCAL_EX_VAR = "LOCAL_EX_VAR"


class WrappedVar:
    """Wraps a TEAL global variable."""

    def __init__(
        self, name, var_type, index=None, app_id=None, name_to_bytes=True
    ):
        self.name = name
        self.var_type = var_type
        self.name_to_bytes = name_to_bytes
        if (
            self.var_type == LOCAL_VAR
            or self.var_type == GLOBAL_EX_VAR
            or self.var_type == LOCAL_EX_VAR
        ):
            assert index, "must pass an index"
            self.index = index
            if self.var_type == LOCAL_EX_VAR:
                assert app_id, "must pass an app id"
                self.app_id = app_id

    def put(self, val):
        """Puts a value into the variable."""

        if self.var_type == GLOBAL_VAR:
            return (
                App.globalPut(Bytes(self.name), val)
                if self.name_to_bytes
                else App.globalPut(self.name, val)
            )
        if self.var_type == LOCAL_VAR:
            return (
                App.localPut(self.index, Bytes(self.name), val)
                if self.name_to_bytes
                else App.localPut(self.index, self.name, val)
            )

    def get(self, app_id=None):
        """Gets a value from the variable."""

        if self.var_type == GLOBAL_VAR:
            return (
                App.globalGet(Bytes(self.name))
                if self.name_to_bytes
                else App.globalGet(self.name)
            )
        if self.var_type == GLOBAL_EX_VAR:
            return (
                App.globalGetEx(self.index, Bytes(self.name))
                if self.name_to_bytes
                else App.globalGetEx(self.index, self.name)
            )
        if self.var_type == LOCAL_VAR:
            return (
                App.localGet(self.index, Bytes(self.name))
                if self.name_to_bytes
                else App.localGet(self.index, self.name)
            )
        if self.var_type == LOCAL_EX_VAR:
            return (
                App.localGetEx(self.index, self.app_id, Bytes(self.name))
                if self.name_to_bytes
                else App.localGetEx(self.index, self.app_id, self.name)
            )

    def delete(self):
        """Deletes the variable."""

        if self.var_type == GLOBAL_VAR:
            return (
                App.globalDel(Bytes(self.name))
                if self.name_to_bytes
                else App.globalDel(self.name)
            )
        if self.var_type == LOCAL_VAR:
            return (
                App.localDel(self.index, Bytes(self.name))
                if self.name_to_bytes
                else App.localDel(self.index, self.name)
            )
