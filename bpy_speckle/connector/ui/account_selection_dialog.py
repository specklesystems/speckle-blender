import bpy
from bpy.types import Context, Event
from ..utils.account_manager import (
    get_account_enum_items,
    speckle_account,
)


class SPECKLE_UL_accounts_list(bpy.types.UIList):
    """
    UIList for displaying accounts
    """

    def draw_item(
        self,
        context: Context,
        layout: bpy.types.UILayout,
        data: bpy.types.PropertyGroup,
        item: bpy.types.PropertyGroup,
        icon: str,
        active_data: bpy.types.PropertyGroup,
        active_propname: str,
    ) -> None:
        if self.layout_type in {"DEFAULT", "COMPACT"}:
            row = layout.row()
            row.label(text=item.user_name)
            row.label(text=item.server_url)
            row.label(text=item.user_email)
        elif self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.user_name)


class SPECKLE_OT_account_selection_dialog(bpy.types.Operator):
    """
    operator for displaying and handling the account selection dialog
    """

    bl_idname = "speckle.account_selection_dialog"
    bl_label = "Select Account"
    bl_description = "Select account"

    account_index: bpy.props.IntProperty(default=0)  # type: ignore

    def invoke(self, context: Context, event: Event) -> set[str]:
        wm = context.window_manager
        # Clear existing accounts
        wm.speckle_accounts.clear()

        # Save selected account
        current_account_index = 0

        # Fetch accounts
        for i, (id, user_name, server_url, user_email) in enumerate(
            get_account_enum_items()
        ):
            account: speckle_account = wm.speckle_accounts.add()
            account.id = id
            account.user_name = user_name
            account.server_url = server_url
            account.user_email = user_email
            if id == wm.selected_account_id:
                current_account_index = i

        self.account_index = current_account_index
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context) -> None:
        layout = self.layout
        layout.label(text="Select account")
        layout.template_list(
            "SPECKLE_UL_accounts_list",
            "",
            context.window_manager,
            "speckle_accounts",
            self,
            "account_index",
        )

    def execute(self, context: Context) -> set[str]:
        wm = context.window_manager
        wm.selected_account_id = wm.speckle_accounts[self.account_index].id
        return {"FINISHED"}
