"""Translation strings for SC4PIM UI."""
chooseParentCohortMsg = 'Choose parent cohort'
resetParentCohortMsg = 'Reset Parent Cohort'
quitMsg = 'Are you sure you want to quit ?'
LERandomTextureMsg = 'Random texture'
LEWealthDependantTextureMsg = 'Wealth dependant texture'
LETreeTools = 'Tools'
LETreeTextures = 'Textures'
LETreeBaseTextures = 'Base textures'
LETreeOverlayTextures = 'Overlay textures'
LETreeProps = 'Props'
LETreePropsByTGI = 'Single by TGI'
LETreePropsByName = 'Single by Name'
LETreePropsFamily = 'Families'
LETreeFlora = 'Flora'
LETreeLot = 'Lot'
LETreeIcon = 'Icon'
LETreePref = 'Preferences'
LEToggleTop = 'Toggle on Top'
LEConfirmDeletGroupMsg = 'Are you sure you want to removed that group'
LEConfirmDeletGroupTitle = 'Group Confirmation'
LEConfirmDeletFamilyMsg = 'Are you sure you want to removed that family'
LEConfirmDeletFamilyTitle = 'Family Confirmation'
LEMenuCreateGroup = 'Create a new group'
LEMenuDeleteGroup = 'Delete that group'
LEMenuDeleteFamily = 'Remove that family'
LEGroupNameDlg = 'Group name'
LEGroupNameDlgTitle = 'Add group'
LEMainTitle = 'LE Tools'
LEXPAN = 'Pan'
LEXProps = 'Props'
LEXBaseTexture = 'Base texture'
LEXOverlayTexture = 'Overlay texture'
LEXBuilding = 'Building'
LEXFlora = 'Flora'
modeNamesMsg = [
 'Full', 'LE-like', 'Transit Enable', 'Water land constraints']
LEXSBDisplayMode = 'Display Mode'
LEXSBDisplayMode0 = 'Full'
LEXSBEditMode = 'Edit Mode'
LEXSBEditMode0 = 'Pan'
LEXSBUnderMouse = 'Under mouse'
LEXSnapGripSize = 'Snap grid size'
LotCreationDlgMsg = 'Lot creation'
LotCreationDlgWidth = 'Width'
LotCreationDlgHeight = 'Height'
LotCreationDlgStage = 'Stage'
DepDlgMissing = "<font color='red'>Missing dependencies</font>"
DepDlgBuildingFoundation = 'Building foundation'
DepDlgBuilding = 'Building'
DepDlgNotFound = 'not found'
DepDlgProps = 'Props'
DepDlgTextures = 'Textures'
DepDlgFlora = 'Flora'
IconDlgTitle = 'Icon maker'
IconDlgPicture = 'Icon picture'
try:
    with open('current.lang') as f:
        exec(f.read())
except IOError:
    pass
treeRootMsg = 'Root'
treeResourceMsg = 'Resources'
treeStdModelMsg = 'BAT Models'
treeOtherModelMsg = 'Other Models'
treeAnimMsg = 'Animations'
treeDescMsg = 'Descriptions'

# -*- coding: iso-8859-15 -*-

popupPropertyMenuItem1 = "Copy properties"
popupPropertyMenuItem2 = "Paste properties"
popupPropertyMenuItem3 = "Delete properties"
popupPropertyMenuItem4 = "Add property"
popupPropertyMenuItem5 = "Add Item Name"
popupPropertyMenuItem6 = "Convert Item name/Examplar name to LTEXT - multilingual"
popupPropertyMenuItem7 = "Add User Visible Name Key LTEXTs"
popupPropertyMenuItem8 = "Add Item Description"
popupPropertyMenuItem9 = "Convert Item Description to LTEXT - multilingual"
popupPropertyMenuItem10 = "Add Item Description Key LTEXTs"
popupPropertyMenuItem12 = "Open all buildings/props related to family"
popupPropertyMenuItem14 = "Recompute properties as %s"
popupPropertyMenuItem16 = "Rebuild the OccupantSize from model"
popupPropertyMenuItem25 = "Add to a family"
popupPropertyMenuItem17 = "Open lot(s) using this building/family"
popupPropertyMenuItem20 = "Convert to RKT0"
popupPropertyMenuItem21 = "Convert to RKT1"
popupPropertyMenuItem24 = "Convert to RKT4"
popupPropertyMenuItem18 = "Open building(s) from this lot"
popupPropertyMenuItem19 = "Lot editor"
popupPropertyMenuItem26 = "Turn into a reward"
popupPropertyMenuItem27 = "Dependencies listing"
popupPropertyMenuItem28 = "Create a growable lot using this building"
popupPropertyMenuItem29 = "Create a plopable lot using this building"
popupPropertyMenuItem30 = "Create an similar growable lot from this plopable"
popupPropertyMenuItem31 = "Recompute stage for this growable lot"
popupPropertyMenuItem34 = "Tileset selector"
popupPropertyMenuItem35 = "Change Icon"
popupPropertyMenuItem36 = "Open lot(s) using this prop/family"


addPropertyMsg = 'Choose a property to add'
addPropertyTitle = 'Add property'

valuePropertyMsg = "Enter new value for %s"

unknownRK = "Unknown resource key"

propertyPageClose = "Close"
propertyPageSave = "Save"

propertyPageColumnName = "Name"
propertyPageColumnNameValue = "Name Value"
propertyPageColumnDataType = "Data type"
propertyPageColumnRep = "Rep"
propertyPageColumnValue = "Value"

propertyPageFilename = "File name"
propertyPageParentCohort = "Parent Cohort"
propertyPageInherited = "Inherited properties"
propertyPageLTEXT = "Related LTEXTs"

propertyPageFamily = "Family properties"


configurationDialogTitle = "Configuration"
configurationDialogGID = "Your GID is 0x%08X"
configurationDialogAddFolder = "Add folder"
configurationDialogRemoveFolder = "Remove folder"

menuItem1 = "&File"
menuItem1_1 = "&Quit"

menuItem2 = "&Advanced"
menuItem2_1 = "Configure"

viewerZoomBest = "Best Fit"
viewerZoom1 = "Zoom 1"
viewerZoom2 = "Zoom 2"
viewerZoom3 = "Zoom 3"
viewerZoom4 = "Zoom 4"
viewerZoom5 = "Zoom 5"

viewerRotSouth = "South"
viewerRotEast = "East"
viewerRotNorth = "North"
viewerRotWest = "West"

viewerModel = "For RKT4"

itemColumName = "Name"
itemColumFilename = "File"
itemColumDate = "Date"

descCreationDialogMsg = "Enter name of the building"
descCreationDialogTitle = "Creation of a building examplar"

loadingDialogMsg = "Initialising"

editUnicodeTitle = "LTEXT edition"
editUnicodeWarning = "Warning, Edited LTEXT will be automatically saved"

invisibleATC = 'Invisible or missing ATC'
unknonwMsg = "Unknown"
invisibleModel = 'Invisible or missing model'
xmlNotFound = '[Xml not found]'

categoryLocalized = {}
categoryLocalized[0xEC8FBA75] = "All"
categoryLocalized[0x6D055E57] = "Foundation"
categoryLocalized[0x0C8FBB55] = "Building"
categoryLocalized[0xD30E71DF] = "Unknown"
categoryLocalized[0xCC8ABC2D] = "Unused"
categoryLocalized[0xAC8FBB73] = "R-C-I"
categoryLocalized[0x0C8FBB86] = "Residential"
categoryLocalized[0x2C8FBB95] = "($) Low Wealth"
categoryLocalized[0x6C8FBBA5] = "($$) Medium Wealth"
categoryLocalized[0x0C8FBBAE] = "($$$) High Wealth"
categoryLocalized[0xAC8FBBBB] = "Commercial Service"
categoryLocalized[0x8C8FBBCC] = "(CS $) Low Wealth"
categoryLocalized[0x0C8FBBDC] = "(CS $$) Medium Wealth"
categoryLocalized[0xAC8FBBEB] = "(CS $$$) High Wealth"
categoryLocalized[0xCCAA4CCE] = "Commercial Office"
categoryLocalized[0x6C8FBBF5] = "(CO $$) Medium Wealth"
categoryLocalized[0xCC8FBC01] = "(CO $$$) High Wealth"
categoryLocalized[0x8C8FBC0B] = "Industrial"
categoryLocalized[0x2CAA4D2A] = "(I-a) Agricultural Industry"
categoryLocalized[0x2C8FBC17] = "(I-d) Dirty Industry"
categoryLocalized[0x2C8FBC18] = "(I-d) Dirty Industry Anchor"
categoryLocalized[0x2C8FBC19] = "(I-d) Dirty Industry Mechanical"
categoryLocalized[0x2C8FBC1A] = "(I-d) Dirty Industry Out"
categoryLocalized[0x6C7E983B] = "(I-m) Manufacturing Industry"
categoryLocalized[0x6C7E983C] = "(I-m) Manufacturing Industry Anchor"
categoryLocalized[0x6C7E983D] = "(I-m) Manufacturing Industry Mechanical"
categoryLocalized[0x6C7E983E] = "(I-m) Manufacturing Industry Out"
categoryLocalized[0x6C8FBDDC] = "(I-ht) High-Tech Industry"
categoryLocalized[0x6C8FBDDD] = "(I-ht) High-Tech Industry Anchor"
categoryLocalized[0x6C8FBDDE] = "(I-ht) High-Tech Industry Mechanical"
categoryLocalized[0x6C8FBDDF] = "(I-ht) High-Tech Industry Out"
categoryLocalized[0xCC8FBC2D] = "Ploppable"
categoryLocalized[0x2C8FBC37] = "Education"
categoryLocalized[0x8C8FBC82] = "Elementary"
categoryLocalized[0xCC8FBC8C] = "High School"
categoryLocalized[0xEC8FBC96] = "Library"
categoryLocalized[0x0C8FBC9F] = "College"
categoryLocalized[0x8CB2360E] = "Museum"
categoryLocalized[0x8C8FBC47] = "Park"
categoryLocalized[0xCCB23662] = "Hospital"
categoryLocalized[0x2CB2368C] = "Fire Station"
categoryLocalized[0x6CB236A7] = "Police"
categoryLocalized[0x6CB236CD] = "Police Station"
categoryLocalized[0x0CB236D3] = "Jail"
categoryLocalized[0x4CB23866] = "Power"
categoryLocalized[0xECB23861] = "Waste To Energy"
categoryLocalized[0xECB23761] = "Recycle"
categoryLocalized[0x6C8FBC50] = "Water"
categoryLocalized[0x4C8FBCCC] = "Pump"
categoryLocalized[0xAC8FBCD7] = "Treatment"
categoryLocalized[0x0C8FBC5E] = "Transportation"
categoryLocalized[0x6C8FBCEF] = "Bus Stop"
categoryLocalized[0x0C8FBCF9] = "Subway Station"
categoryLocalized[0x0C8FBD07] = "Passenger Rail Station"
categoryLocalized[0x6C8FBD13] = "Freight Rail Station"
categoryLocalized[0x0C8FBD1C] = "Airport"
categoryLocalized[0xCCB2391F] = "Seaport"
categoryLocalized[0xACB23926] = "Toll Booth"
categoryLocalized[0x6CB2392A] = "Passenger Ferry Terminal"
categoryLocalized[0xECBB8AB8] = "Car Ferry Terminal"
categoryLocalized[0xACBB8BB5] = "Garage"
categoryLocalized[0x4CB2392F] = "Elevated Rail Station"
categoryLocalized[0x0CB23934] = "Monorail Station"
categoryLocalized[0x2C8FBC6C] = "Landmark"
categoryLocalized[0x3C8FAC6C] = "All Landmarks"
categoryLocalized[0x1C8FBC6C] = "Landmark EyeCandy"
categoryLocalized[0x3C8FBC6C] = "Landmark WithJobs"
categoryLocalized[0x3C8F5C6C] = "Landmark With CS$ Jobs"
categoryLocalized[0x3C8F5D6C] = "Landmark With CS$$ Jobs"
categoryLocalized[0x3C8F5E6C] = "Landmark With CS$$$ Jobs"
categoryLocalized[0x3C8F5F6C] = "Landmark With CO$$ Jobs"
categoryLocalized[0x3C8F506C] = "Landmark With CO$$$ Jobs"
categoryLocalized[0x3C8F516C] = "Landmark With I-Agr Jobs"
categoryLocalized[0x3C8F526C] = "Landmark With I-D Jobs"
categoryLocalized[0x3C8F536C] = "Landmark With I-M Jobs"
categoryLocalized[0x3C8F546C] = "Landmark With I-HT Jobs"
categoryLocalized[0x2D8FBC6C] = "Reward"
categoryLocalized[0x0C8FBD24] = "Prop"
categoryLocalized[0xDC8FBB83] = "All"
categoryLocalized[0xF3BA7221] = "Families"
categoryLocalized[0xF3BA8221] = "Named Families"
categoryLocalized[0xF3BA8521] = "Unnamed Families"
categoryLocalized[0x6d155e57] = "Flora"
categoryLocalized[0x6d155f57] = "WaterFront"

namedLang = [ "Default international",
              "US English",
              "UK English",
              "French",
              "German",
              "Italian",
              "Spanish",
              "Dutch",
              "Danish",
              "Swedish",
              "Norwegian",
              "Finnish",
              "Japanese",
              "Polish",
              "Traditional Chinese",
              "Simplified Chinese",
              "Thai",
              "Korean",
              "Portugese" ]

chooseFolderMsg = "Choose a folder:"

fillingDegreeMsg = "Enter the filling degree of the building ( 0 - 1 )"
fillingDegreeTitleMsg = "Filling degree"

DependenciesDlgTitleMsg = "Dependencies"

chooseParentCohortMsg = 'Choose parent cohort'
resetParentCohortMsg = 'Reset Parent Cohort'
quitMsg = "Are you sure you want to quit ?"

LERandomTextureMsg = "Random texture"
LEWealthDependantTextureMsg = "Wealth dependant texture"
LETreeTools = "Tools"
LETreeTextures = "Textures"
LETreeBaseTextures ="Base textures"
LETreeOverlayTextures ="Overlay textures"
LETreeProps = "Props"
LETreePropsByTGI = "Single by TGI"
LETreePropsByName = "Single by Name"
LETreePropsFamily = "Families"
LETreeFlora = "Flora"
LETreeLot = "Lot"
LETreeIcon = "Icon"
LETreePref = "Preferences"
LEToggleTop = "Toggle on Top"

LEConfirmDeletGroupMsg = 'Are you sure you want to removed that group'
LEConfirmDeletGroupTitle = 'Group Confirmation'
LEConfirmDeletFamilyMsg = 'Are you sure you want to removed that family'
LEConfirmDeletFamilyTitle = 'Family Confirmation'
LEMenuCreateGroup = "Create a new group"
LEMenuDeleteGroup = "Delete that group"
LEMenuDeleteFamily = "Remove that family"
LEGroupNameDlg = 'Group name'
LEGroupNameDlgTitle = 'Add group'
LEMainTitle = 'LE Tools'

LEXPAN = 'Pan'
LEXProps = 'Props'
LEXBaseTexture = "Base texture"
LEXOverlayTexture = "Overlay texture"
LEXBuilding = 'Building'
LEXFlora = "Flora"

modeNamesMsg = ['Full','LE-like','Transit Enable','Water land constraints']
LEXSBDisplayMode = 'Display Mode'
LEXSBDisplayMode0 = 'Full'
LEXSBEditMode = 'Edit Mode'
LEXSBEditMode0 = 'Pan'
LEXSBUnderMouse = 'Under mouse'
LEXSnapGripSize = 'Snap grid size'

LotCreationDlgMsg = 'Lot creation'
LotCreationDlgWidth = 'Width'
LotCreationDlgHeight = 'Height'
LotCreationDlgStage = 'Stage'

DepDlgMissing = "<font color='red'>Missing dependencies</font>"
DepDlgBuildingFoundation = 'Building foundation'
DepDlgBuilding = 'Building'
DepDlgNotFound= 'not found'
DepDlgProps = 'Props'
DepDlgTextures = 'Textures'
DepDlgFlora = 'Flora'

IconDlgTitle= "Icon maker"
IconDlgPicture = "Icon picture"