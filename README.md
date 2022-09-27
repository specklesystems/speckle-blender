<h1 align="center">
  <img src="https://user-images.githubusercontent.com/2679513/131189167-18ea5fe1-c578-47f6-9785-3748178e4312.png" width="150px"/><br/>
  Speckle | Blender
</h1>
<h3 align="center">
    Connector for Blender
</h3>
<p align="center"><b>Speckle</b> is the data infrastructure for the AEC industry.</p><br/>

<p align="center"><a href="https://twitter.com/SpeckleSystems"><img src="https://img.shields.io/twitter/follow/SpeckleSystems?style=social" alt="Twitter Follow"></a> <a href="https://speckle.community"><img src="https://img.shields.io/discourse/users?server=https%3A%2F%2Fspeckle.community&amp;style=flat-square&amp;logo=discourse&amp;logoColor=white" alt="Community forum users"></a> <a href="https://speckle.systems"><img src="https://img.shields.io/badge/https://-speckle.systems-royalblue?style=flat-square" alt="website"></a> <a href="https://speckle.guide/dev/"><img src="https://img.shields.io/badge/docs-speckle.guide-orange?style=flat-square&amp;logo=read-the-docs&amp;logoColor=white" alt="docs"></a></p>
<p align="center"><a href="https://github.com/specklesystems/speckle-blender/"><img src="https://circleci.com/gh/specklesystems/speckle-blender.svg?style=svg&amp;circle-token=76eabd350ea243575cbb258b746ed3f471f7ac29" alt="Speckle-Next"></a> </p>

# About Speckle

What is Speckle? Check our ![YouTube Video Views](https://img.shields.io/youtube/views/B9humiSpHzM?label=Speckle%20in%201%20minute%20video&style=social)

### Features

- **Object-based:** say goodbye to files! Speckle is the first object based platform for the AEC industry
- **Version control:** Speckle is the Git & Hub for geometry and BIM data
- **Collaboration:** share your designs collaborate with others
- **3D Viewer:** see your CAD and BIM models online, share and embed them anywhere
- **Interoperability:** get your CAD and BIM models into other software without exporting or importing
- **Real time:** get real time updates and notifications and changes
- **GraphQL API:** get what you need anywhere you want it
- **Webhooks:** the base for a automation and next-gen pipelines
- **Built for developers:** we are building Speckle with developers in mind and got tools for every stack
- **Built for the AEC industry:** Speckle connectors are plugins for the most common software used in the industry such as Revit, Rhino, Grasshopper, AutoCAD, Civil 3D, Excel, Unreal Engine, Unity, QGIS, Blender and more!

### Try Speckle now!

Give Speckle a try in no time by:

- [![speckle XYZ](https://img.shields.io/badge/https://-speckle.xyz-0069ff?style=flat-square&logo=hackthebox&logoColor=white)](https://speckle.xyz) ⇒ creating an account at our public server
- [![create a droplet](https://img.shields.io/badge/Create%20a%20Droplet-0069ff?style=flat-square&logo=digitalocean&logoColor=white)](https://marketplace.digitalocean.com/apps/speckle-server?refcode=947a2b5d7dc1) ⇒ deploying an instance in 1 click 

### Resources

- [![Community forum users](https://img.shields.io/badge/community-forum-green?style=for-the-badge&logo=discourse&logoColor=white)](https://speckle.community) for help, feature requests or just to hang with other speckle enthusiasts, check out our community forum!
- [![website](https://img.shields.io/badge/tutorials-speckle.systems-royalblue?style=for-the-badge&logo=youtube)](https://speckle.systems) our tutorials portal is full of resources to get you started using Speckle
- [![docs](https://img.shields.io/badge/docs-speckle.guide-orange?style=for-the-badge&logo=read-the-docs&logoColor=white)](https://speckle.guide/user/blender.html) reference on almost any end-user and developer functionality


# Repo structure

The Speckle UI can be found in the 3d viewport toolbar (N), under the Speckle tab.

Head to the [**📚 documentation**](https://speckle.guide/user/blender.html) for more information.

## Disclaimer
This code is WIP and as such should be used with extreme caution on non-sensitive projects.

## Installation

1. Place `bpy_speckle` folder in your `addons` folder. On Windows this is typically `%APPDATA%/Blender Foundation/Blender/2.80/scripts/addons`.
2. Go to `Edit->Preferences` (Ctrl + Alt + U)
3. Go to the `Add-ons` tab
4. Find and enable `SpeckleBlender 2.0` in the `Scene` category. <!-- **If enabling for the first time, expect the UI to freeze for bit while it silently installs all the dependencies.** -->
5. The Speckle UI can be found in the 3d viewport toolbar (N), under the `Speckle` tab.

## Usage
- Available user accounts are automatically detected and made available. To add user accounts use **Speckle Manager**.
- Select the user from the dropdown list in the `Users` panel. This will populate the `Streams` list with available streams for the selected user.
- Select a branch and commit from the dropdown menus.
- Click on `Receive` to download the objects from the selected stream, branch, and commit. The stream objects will be loaded into a Blender Collection, named `<STREAM_NAME> [ <STREAM_BRANCH> @ <BRANCH_COMMIT> ]`. <!-- You can filter the stream by entering a query into the `Filter` field (i.e. `properties.weight>10` or `type="Mesh"`). -->
- Click on `Open Stream in Web` to view the stream in your web browser.

## Caveats

- Mesh objects are supported. Breps are imported as meshes using their `displayValue` data. 
- Curves have limited support: `Polylines` are supported; `NurbsCurves` are supported, though they are not guaranteed to look the same; `Lines` are supported; `Arcs` are not supported, though they are very roughly approximated; `PolyCurves` are supported for linear / polyline segments and very approximate arc segments. These conversions are a point of focus for further development.

## Custom properties

- **SpeckleBlender** will look for a `texture_coordinates` property and use that to create a UV layer for the imported object. These texture coordinates are a space-separated list of floats (`[u v u v u v etc...]`) that is encoded as a base64 blob. This is subject to change as **SpeckleBlender** develops.
- If a `renderMaterial` property is found, **SpeckleBlender** will create a material named using the sub-property `renderMaterial.name`. If a material with that name already exists in Blender, **SpeckleBlender** will just assign that existing material to the object. This allows geometry to be updated without having to re-assign and re-create materials.
- Vertex colors are supported. The `colors` list from Speckle meshes is translated to a vertex color layer.
- Speckle properties will be imported as custom properties on Blender objects. Nested dictionaries are expanded to individual properties by flattening their key hierarchy. I.e. `propA:{'propB': {'propC':10, 'propD':'foobar'}}` is flattened to `propA.propB.propC = 10` and `propA.propB.propD = "foobar"`.


## Contributing

Please make sure you read the [contribution guidelines](.github/CONTRIBUTING.md) for an overview of the best practices we try to follow.

## Community

The Speckle Community hangs out on [the forum](https://discourse.speckle.works), do join and introduce yourself & feel free to ask us questions!

## License

Unless otherwise described, the code in this repository is licensed under the Apache-2.0 License. Please note that some modules, extensions or code herein might be otherwise licensed. This is indicated either in the root of the containing folder under a different license file, or in the respective file's header. If you have any questions, don't hesitate to get in touch with us via [email](mailto:hello@speckle.systems).

## Notes
SpeckleBlender is written and maintained by [Tom Svilans](http://tomsvilans.com) ([Github](https://github.com/tsvilans)).
