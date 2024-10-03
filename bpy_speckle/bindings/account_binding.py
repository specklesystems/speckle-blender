import bpy
from specklepy.api.credentials import get_local_accounts, get_default_account

class SpeckleAccount(bpy.types.PropertyGroup):
    id: bpy.props.StringProperty()
    name: bpy.props.StringProperty()

class AccountBinding(bpy.types.PropertyGroup):
    accounts: bpy.props.CollectionProperty(type=SpeckleAccount)
    active_account: bpy.props.PointerProperty(type=SpeckleAccount)

    def get_local_accounts(self):
        self.accounts.clear()
        local_accounts = get_local_accounts()
        for acc in local_accounts:
            account = self.accounts.add()
            account.id = acc.id
            account.name = acc.userInfo.name
        if self.accounts:
            self.set_active_account(get_default_account())
    
    def get_default_account(self):
        return get_default_account()

    def set_active_account(self, account):
        self.active_account = account
    
    def get_account_infos(self):
        return [(acc.id, acc.name, "") for acc in self.accounts]
    
def register():
    bpy.utils.register_class(SpeckleAccount)
    bpy.utils.register_class(AccountBinding)

def unregister():
    bpy.utils.unregister_class(SpeckleAccount)
    bpy.utils.unregister_class(AccountBinding)

