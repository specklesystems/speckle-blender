# SpeckleBlender 2.0
Speckle add-on for Blender 2.92

[![Twitter Follow](https://img.shields.io/twitter/follow/SpeckleSystems?style=social)](https://twitter.com/SpeckleSystems) [![Community forum users](https://img.shields.io/discourse/users?server=https%3A%2F%2Fdiscourse.speckle.works&style=flat-square&logo=discourse&logoColor=white)](https://discourse.speckle.works) [![website](https://img.shields.io/badge/https://-speckle.systems-royalblue?style=flat-square)](https://speckle.systems) [![docs](https://img.shields.io/badge/docs-speckle.guide-orange?style=flat-square&logo=read-the-docs&logoColor=white)](https://speckle.guide/dev/)

## Introduction

The Speckle UI can be found in the 3d viewport toolbar (N), under the Speckle tab.
<!--
This repo holds Speckle's:

- Default [Code of Conduct](.github/CODE_OF_CONDUCT.md),
- Default [Contribution Guidelines](.github/CONTRIBUTING.md),
- README template (you're reading it now),
- Default [Issue Template](.github/ISSUE_TEMPLATE/ISSUE_TEMPLATE.md),
- Default [Pull Request Template](.github/PULL_REQUEST_TEMPLATE/PR_TEMPLATE.md),
- OSS License (Apache 2.0)

Either copy paste the parts that are useful in existing repos, or use this as a base when creating a new repository.
-->

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
- Click on `View stream data (API)` to view the stream in your web browser.

## Caveats

- Mesh objects are supported. Breps are imported as meshes using their `displayValue` data. 
- Curves have limited support: `Polylines` are supported; `NurbsCurves` are supported, though they are not guaranteed to look the same; `Lines` are supported; `Arcs` are not supported, though they are very roughly approximated; `PolyCurves` are supported for linear / polyline segments and very approximate arc segments. These conversions are a point of focus for further development.

## Custom properties

- **SpeckleBlender** will look for a `texture_coordinates` property and use that to create a UV layer for the imported object. These texture coordinates are a space-separated list of floats (`[u v u v u v etc...]`) that is encoded as a base64 blob. This is subject to change as **SpeckleBlender** develops.
- If a `material` property is found, **SpeckleBlender** will create a material named using the sub-property `material.name`. If a material with that name already exists in Blender, **SpeckleBlender** will just assign that existing material to the object. This allows geometry to be updated without having to re-assign and re-create materials.
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
