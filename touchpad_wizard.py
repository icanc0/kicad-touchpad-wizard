from pcbnew import *
import FootprintWizardBase
import pcbnew

class TrackpadWizard(FootprintWizardBase.FootprintWizard):

    def GetName(self):
        return 'Trackpad'

    def GetDescription(self):
        return 'Capacitive Trackpad wizard'

    def GetValue(self):
        return "Trackpad-{w:g}x{h:g}mm".format(
            w = pcbnew.ToMM(self.pads['width']),
            h = pcbnew.ToMM(self.pads['height'])
        )

    def GenerateParameterList(self):
        self.AddParam("Trackpad", "width", self.uMM, 50)
        self.AddParam("Trackpad", "height", self.uMM, 20)
        self.AddParam("Trackpad", "edge segments x", self.uInteger, 5, min_value=4)
        self.AddParam("Trackpad", "edge segments y", self.uInteger, 5, min_value=4)
        self.AddParam("Trackpad", "via diameter", self.uMM, 0.5, min_value=0.2)
        self.AddParam("Trackpad", "via drill", self.uMM, 0.2, min_value=0.1)
        self.AddParam("Trackpad", "clearance", self.uMM, 0.2)
        self.AddParam("Trackpad", "line width", self.uMM, 0.127, min_value=0.1)

        self.AddParam("Options",  "drill hole", self.uBool, True)
        self.AddParam("Options",  "add lines", self.uBool, True)
        self.AddParam("Options",  "add front wiring", self.uBool, True)
        self.AddParam("Options",  "add back wiring", self.uBool, True)

        self.AddParam("Triangle debug", "debug", self.uBool, True)
        self.AddParam("Triangle debug", "angle", self.uInteger, 135, min_value=0, max_value=360)

    @property
    def pads(self):
        return self.parameters['Trackpad']

    def smdTrianglePad(self, module, size, pos, name, rotation):
        pad = PAD(module)
        pad.SetSize(VECTOR2I(size[0], size[1]))
        pad.SetShape(PAD_SHAPE_TRAPEZOID) 
        pad.SetAttribute(PAD_ATTRIB_SMD)
        pad.SetLayerSet(pad.ConnSMDMask())
        pad.SetPosition(pos)
        pad.SetName(name)
        pad.SetOrientation(pcbnew.EDA_ANGLE(rotation * 10))  # wtf is proper units!!!

        if self.parameters['Triangle debug']["debug"]:
            pad.SetDelta(VECTOR2I(size[1], 0))  # mfw MFW MFW MFW

        return pad
    
    def AddVia(self, module, pos, size, drill, name):
        via = PAD(module)
        via.SetSize(VECTOR2I(size, size))
        via.SetShape(PAD_SHAPE_CIRCLE)
        via.SetAttribute(PAD_ATTRIB_PTH)
        via.SetDrillSize(VECTOR2I(drill, drill))
        via.SetLayerSet(via.PTHMask())
        via.SetPosition(pos)
        via.SetName(name)
        module.Add(via)

    def DrawHorizontalLine(self, start, end, layer):
        line = pcbnew.PCB_SHAPE(self.module)
        line.SetShape(SHAPE_T_SEGMENT)
        line.SetStart(start)
        line.SetEnd(end)
        line.SetLayer(layer)
        line.SetWidth(int(self.pads["line width"]))
        self.module.Add(line)

    def CheckParameters(self):
        pass

    def BuildAll(self):
        module = self.module
        width = self.pads["width"]
        height = self.pads["height"]
        
        edge_segments_x = self.pads["edge segments x"]
        edge_segments_y = self.pads["edge segments y"]

        clearance = self.pads["clearance"]
        half_clearance = clearance / 2

        # for pads, further subdivision is needed since 4 pads occupy 1/4 of each grid
        pad_width = width / (edge_segments_x * 2 )
        pad_height = height / (edge_segments_y * 2)

        via_size = self.pads["via diameter"]
        via_drill = self.pads["via drill"]

        # Top 
        for i in range(edge_segments_x):
            x = -width/2 + i * (pad_width * 2) + pad_width

            for j in range(0, edge_segments_y):
                y = -height/2 + pad_height/2 + j * (pad_height * 2)
                
                pos = VECTOR2I(int(x), int(y - half_clearance))
                pad = self.smdTrianglePad(module, (int(pad_height  - clearance), int(pad_width - clearance)), pos, "c" + str(i), 135) # 135
                module.Add(pad)
                # drill hole at the center

                if self.parameters['Options']["drill hole"]:
                    via_pos = VECTOR2I(int(x), int(y))
                    self.AddVia(module, via_pos, via_size, via_drill, "v_c" + str(i))

                if self.parameters['Options']["add back wiring"]:
                    self.DrawHorizontalLine(VECTOR2I(int(x), int(y + pad_height + clearance)), VECTOR2I(int(x), int(y)), pcbnew.B_Cu)

        # Right 
        for i in range(edge_segments_y):
            y = -height/2 + i * (pad_height * 2) + pad_height

            for j in range(0, edge_segments_x):
                x = width/2 - pad_width/2 - j * (pad_width * 2)
                pos = VECTOR2I(int(x + half_clearance), int(y))
                pad = self.smdTrianglePad(module, (int(pad_width - clearance), int(pad_height - clearance)), pos, "r" + str(i), 90) # 270
                module.Add(pad)

        # Bottom 
        for i in range(edge_segments_x):
            x = -width/2 + i * (pad_width * 2) + pad_width

            for j in range(0, edge_segments_y):
                y = height/2 - pad_height/2 - j * (pad_height * 2)
                pos = VECTOR2I(int(x), int(y + half_clearance))
                pad = self.smdTrianglePad(module, (int(pad_height - clearance), int(pad_width - clearance)), pos, "c" + str(i), 45) # 45
                module.Add(pad)

                if self.parameters['Options']["drill hole"]:
                    via_pos = VECTOR2I(int(x), int(y))
                    self.AddVia(module, via_pos, via_size, via_drill, "v_c" + str(i))

        # Left 
        for i in range(edge_segments_y):
            y = -height/2 + i * (pad_height * 2) + pad_height

            if self.parameters['Options']["add front wiring"]:
                self.DrawHorizontalLine(VECTOR2I(int(-width/2), int(y)), VECTOR2I(int(width/2), int(y)), pcbnew.F_Cu)
            
            for j in range(0, edge_segments_x):

                x = -width/2 + pad_width/2 + j * (pad_width * 2)
                pos = VECTOR2I(int(x - half_clearance), int(y))
                pad = self.smdTrianglePad(module, (int(pad_width - clearance), int(pad_height - clearance)), pos, "r" + str(i), 0) # 180
                module.Add(pad)

    def BuildThisFootprint(self):
        height = self.pads["height"]

        self.BuildAll()

        # (i copied this from touch slider wizard LMAO) 
        self.module.SetAttributes(FP_SMD)
        
        t_size = self.GetTextSize()
        w_text = self.draw.GetLineThickness()
        self.draw.Value(0, height/2 + t_size/2 + w_text, t_size)
        self.draw.Reference(0, -height/2 - t_size/2 - w_text, t_size)

TrackpadWizard().register()