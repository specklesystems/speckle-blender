import bpy
from bpy.types import Operator
from bpy.props import StringProperty

class SPECKLE_OT_select_objects(Operator):
    """Select all objects imported from this Speckle model"""
    bl_idname = "speckle.select_objects"
    bl_label = "Select Objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    model_card_id: StringProperty(
        name="Model Card ID",
        description="ID of the model card",
        default=""
    )
    
    def execute(self, context):
        # Get the model card
        model_card = context.scene.speckle_state.get_model_card_by_id(self.model_card_id)
        if model_card is None:
            self.report({'ERROR'}, "Model card not found")
            return {'CANCELLED'}
        
        # Construct collection name
        collection_name = f"{model_card.model_name} - {model_card.version_id[:8]}"
        
        # Find the collection
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            self.report({'ERROR'}, f"Collection {collection_name} not found")
            return {'CANCELLED'}
            
        # Deselect all objects first
        bpy.ops.object.select_all(action='DESELECT')
        
        # Select all objects in the collection and its child collections
        def select_collection_objects(collection):
            for obj in collection.objects:
                obj.select_set(True)
            for child in collection.children:
                select_collection_objects(child)
        
        select_collection_objects(collection)
        
        # Set active object to first selected object if any objects were selected
        selected = context.selected_objects
        if selected:
            context.view_layer.objects.active = selected[0]
            # Frame selected objects in the viewport
            bpy.ops.view3d.view_selected()
            
        self.report({'INFO'}, f"Selected {len(context.selected_objects)} objects")
        return {'FINISHED'}