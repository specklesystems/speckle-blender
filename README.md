<<h1 align="center">
  <img src="https://user-images.githubusercontent.com/2679513/131189167-18ea5fe1-c578-47f6-9785-3748178e4312.png" width="150px"/><br/>
  Speckle | Blender
</h1>

<p align="center"><a href="https://twitter.com/SpeckleSystems"><img src="https://img.shields.io/twitter/follow/SpeckleSystems?style=social" alt="Twitter Follow"></a> <a href="https://speckle.community"><img src="https://img.shields.io/discourse/users?server=https%3A%2F%2Fspeckle.community&amp;style=flat-square&amp;logo=discourse&amp;logoColor=white" alt="Community forum users"></a> <a href="https://speckle.systems"><img src="https://img.shields.io/badge/https://-speckle.systems-royalblue?style=flat-square" alt="website"></a> <a href="https://speckle.guide/dev/"><img src="https://img.shields.io/badge/docs-speckle.guide-orange?style=flat-square&amp;logo=read-the-docs&amp;logoColor=white" alt="docs"></a></p>

> Speckle is the first AEC data hub that connects with your favorite AEC tools. Speckle exists to overcome the challenges of working in a fragmented industry where communication, creative workflows, and the exchange of data are often hindered by siloed software and processes. It is here to make the industry better.

<h3 align="center">
    Speckle Connector for Blender
</h3>

> [!WARNING]
> This is a legacy repo! A new next generation connector will be coming soon. In the meantime, check out our active next generation repos here 👇<br/>
> [`speckle-sharp-connectors`](https://github.com/specklesystems/speckle-sharp-connectors): our .NET next generation connectors and desktop UI<br/>
> [`speckle-sharp-sdk`](https://github.com/specklesystems/speckle-sharp-sdk): our .NET SDK, Tests, and Objects

# Blender Connector

The Speckle UI can be found in the 3d viewport toolbar (N), under the Speckle tab.

Head to the [**📚 documentation**](https://speckle.guide/user/blender.html) for more information.

## Installation

We officially support Blender 3.3 and newer, on Windows and Mac.

Please follow our installation instructions on our [connector docs](https://speckle.guide/user/blender.html#installation)

## Usage
Once enabled in `Preferences -> Addons`,
The Speckle connector UI can be found in the 3d viewport toolbar (N), under the `Speckle` tab.

- Available user accounts are automatically detected and made available. To add user accounts use **Speckle Manager**.
- Select the user from the dropdown list in the `Users` panel. This will populate the `Projects` list with available projects for the selected user account.
- Select a model and version from the dropdown menus.
- Click on `Receive` to download and convert the objects from the selected model version. The objects will be linked into a Blender Collection, named `<PROJECT_NAME> [ <MODEL_NAME> @ <VERSION_ID> ]`.
- Click on `Open Model in Web` to view the model in your web browser.

## Supported Elements

The Blender Connector is still a work in progress and, as such, data sent from the Blender connector is a highly lossy exchange. Our connectors are ever evolving to facilitate more and more Speckle usecases. We welcome feedback, requests, edge cases, and contributions!

The full matrix of supported Blender and Speckle types [can be found here](https://speckle.guide/user/support-tables.html#blender)


## Additional Features

- Speckle properties will be imported as custom properties on Blender objects. Nested dictionaries are expanded to individual properties by flattening their key hierarchy. I.e. `propA:{'propB': {'propC':10, 'propD':'foobar'}}` is flattened to `propA.propB.propC = 10` and `propA.propB.propD = "foobar"`.

- If a `renderMaterial` property is found, **SpeckleBlender** will create a material named using the sub-property `renderMaterial.name`. If a material with that name already exists in Blender, **SpeckleBlender** will just assign that existing material to the object. This allows geometry to be updated without having to re-assign and re-create materials.

- Receiving vertex colors is supported. The `colors` list from Speckle meshes is translated to a vertex color layer.

- Receive/Send scripts. Allow injecting a custom python function to the receive/send process to automate any blender operations

## Dependency Installation and Compatibility with Other Blender Addons

Upon first launch of the addon, the Speckle connector installs its SpecklePy dependencies in `%appdata%/Speckle/connector_installations` on Windows and `~/.config/Speckle/connector_installations` on Mac.
This is done through our [`installer.py`](https://github.com/specklesystems/speckle-blender/blob/main/bpy_speckle/installer.py). Through pip, we install the correct version of each dependency for your blender python version, host OS, and system architecture.
As such, an internet connection is required for first launch of the connector.

Other blender addons may require dependencies that conflict with specklepy. In these cases, one or both addons may fail to load.
If you suspect you're seeing a conflict, Please uninstall other third party addons one at a time to identify which addon is conflicting.

If you find an addon that conflicts, please try using a different version of that addon (newer or older).

If you can't find a version of an addon that works, please let us know on [our forums](https://speckle.community/) the name of the addon, the versions you've tried, the version of the Speckle connector you've tried, and your OS (win/mac/linux).

## Contributing

Please make sure you read the [contribution guidelines](.github/CONTRIBUTING.md) for an overview of the best practices we try to follow.

## Community

The Speckle Community hangs out on [the forum](https://discourse.speckle.works), do join and introduce yourself & feel free to ask us questions!

## License

Unless otherwise described, the code in this repository is licensed under the Apache-2.0 License. Please note that some modules, extensions or code herein might be otherwise licensed. This is indicated either in the root of the containing folder under a different license file, or in the respective file's header. If you have any questions, don't hesitate to get in touch with us via [email](mailto:hello@speckle.systems).

## Notes
Thanks to [Tom Svilans](http://tomsvilans.com) ([Github](https://github.com/tsvilans)) for the original v1 contribution!
