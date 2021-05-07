:: get dynamic version and build inno installer bc circleci cmd support sucks
set /p version=<speckle-sharp-ci-tools\Installers\blender\version.txt
echo %version%
speckle-sharp-ci-tools\InnoSetup\ISCC.exe speckle-sharp-ci-tools\blender.iss /dAppVersion=%version%