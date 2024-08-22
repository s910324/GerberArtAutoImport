import os
import re
import sys
import pya
from   os           import listdir
from   os.path      import isfile, join

def artToPCB(folderPath):
    fileNames = [f.split(".")[0] for f in listdir(folderPath) if f.lower().endswith("art")]
    mapping   = genLayerMapping(fileNames)
    template  = xml_template(mapping)
    pcb_path  = os.path.join(folderPath, "combined.pcb")
    
    with open(pcb_path, 'w') as file:
        file.write(template)
    return pcb_path, mapping
    
def loadPCB(pcb_path, top_cell_name = "TOP"):
    print("loadPCB", pcb_path)
    layoutView_pcb = pya.LayoutView()
    cellView_pcb   = layoutView_pcb.cellview(layoutView_pcb.load_layout(pcb_path))
    layout_pcb     = cellView_pcb.layout()
    cell_pcb       = layout_pcb.cell(top_cell_name)
    return layoutView_pcb, cell_pcb
    
def createGDS(top_cell_name = "TOP"):
    mainWindow     = pya.Application.instance().main_window()
    viewID         = mainWindow.create_view()
    layoutView_gds = mainWindow.view(viewID)
    cellView_gds   = layoutView_gds.cellview(layoutView_gds.create_layout(True))
    layout_gds     = cellView_gds.layout()
    cell_gds       = layout_gds.create_cell(top_cell_name)
    cellView_gds.set_cell_name(cell_gds.name)
    mainWindow.current_view_index = viewID
    return layoutView_gds, cell_gds
    
def combineART(folderPath):
    print("combineART", folderPath)
    pcb_path,       mapping  = artToPCB(folderPath)
    layoutView_pcb, cell_pcb = loadPCB(pcb_path, "PCB")
    layoutView_gds, cell_gds = createGDS("PCB")

    for fileName in mapping:
        maplid    = mapping[fileName]["layer"]
        mapname   = mapping[fileName]["layer_name"]
        splitRegs = cnvCircuitReg(cell_pcb, mergeLayer = maplid[0:2], drill = ("drill" in fileName.lower()))               
        cell_gds.shapes(cell_gds.layout().layer(*maplid, mapname)).insert(splitRegs["route"])
        cell_gds.shapes(cell_gds.layout().layer(  0,  0, "EDGE" )).insert(splitRegs["cut"])
        
    layoutView_pcb.close()
    layoutView_gds.add_missing_layers()
    
def cnvCircuitReg(cell, mergeLayer = [1, 0], drill = False):
    cell.flatten(True)
    splitWidth = 11
    bboxMin    = 0
    bboxMax    = 20000
    layout     = cell.layout()
    um         = 1/layout.dbu    
    mlid       = layout.layer(*mergeLayer)
    
    mergedReg  = pya.Region([shape.polygon for shape in cell.each_shape(mlid) if shape.polygon])
    txtReg     = mergedReg.holes().sized(200 * um).merged().sized(-200 * um)
    txtDRC     = txtReg.with_bbox_width(bboxMin * um, bboxMax * um, True)
    drawReg    = mergedReg.not_interacting(txtDRC)
    routeReg, cutlineReg = drawReg.split_inside(pya.Region(drawReg.bbox()).sized(-1))
    
    if drill:
        routeReg = pya.Region([pya.Polygon(p.bbox()) for p in routeReg.each()]).rounded_corners(150 * um, 150 * um, 64)
    return {"route" : routeReg, "cut" : cutlineReg}
    
def genLayerMapping(fileNames):
    mapping      = {}
    bottomLn     = 0
    match_fNames = [f.upper().replace("-", "").replace("_", "") for f in fileNames]
    for i, match_fName in enumerate(match_fNames):
        fileName    = fileNames[i]
        match_out   = (match_fName == "OUTLINE")
        match_top   = (match_fName == "TOP")
        match_top_s = (match_fName == "SST")
        match_layer = re.findall(r"L(\d)$", match_fName)
        match_drill = re.findall(r"DRILL(\d{1})(\d{1})$", match_fName)
        match_silk  = re.findall(r"SS(\d)$", match_fName)
        
        if match_out:
            mapping[fileName] = {"layer" : [    0, 0], "layer_name" : "OUTLINE"}

        if match_top:
            mapping[fileName] = {"layer" : [    1, 0], "layer_name" : "TOP"}
            
        if match_top_s:
            mapping[fileName] = {"layer" : [ 1000, 0], "layer_name" : "SST"}
            
        if match_layer:
            ln = int(match_layer[0])
            mapping[fileName] = {"layer" : [   ln, 0], "layer_name" : f"L{ln}"}
            bottomLn = ln if (ln > bottomLn) else bottomLn
             
        if match_drill:
            ln1 = int(match_drill[0][0])
            ln2 = int(match_drill[0][1])
            mapping[fileName] = {"layer" : [ ln1 * 100 + ln2, 0], "layer_name" : f"DRILL{ln1}{ln2}"} 
            
        if match_silk:
            ln = int(match_silk[0])
            mapping[fileName] = {"layer" : [ ln * 1000, 0], "layer_name" : f"SS{ln}"} 
                                  
    bottomLn = bottomLn + 1

    if "BOTTOM" in match_fNames:
        mapping["BOTTOM"] = {"layer" : [ bottomLn, 0], "layer_name" : "BOTTOM"} 
        
    if "SSB" in match_fNames:
        mapping["SSB"]    = {"layer" : [ bottomLn * 1000, 0], "layer_name" : "SSB"} 
   
    return mapping
    
def xml_template(file_layer_dict):
    free_layer_str = lambda lndt : f"<layout-layer>{lndt[0]}/{lndt[1]}</layout-layer>"
    free_file_str  = lambda filename, layer_index : f"<free-file><filename>{filename}.art</filename><layout-layers><index>{layer_index}</index></layout-layers></free-file>"
    layer_list_str = "\n".join([ free_layer_str(file_layer_dict[filename]["layer"]) for index, filename in enumerate(file_layer_dict) ])
    file_list_str  = "\n".join([ free_file_str (filename, index)                    for index, filename in enumerate(file_layer_dict) ])
    return f'''<?xml version="1.0" encoding="utf-8"?>\n<pcb-project>\n<free-layer-mapping>true</free-layer-mapping>\n<layout-layers>\n{layer_list_str}\n</layout-layers>\n<free-files>\n{file_list_str}\n</free-files>\n<merge-flag>true</merge-flag><dbu>0.001</dbu><cell-name>PCB</cell-name>\n</pcb-project>'''



def openArtFile():
    dialog          = pya.QFileDialog()
    dialog.setFileMode(pya.QFileDialog.Directory)
    dialog.setWindowTitle('Open ART folder...') 
    d = dialog.getExistingDirectory()
    if d : combineART(d)


