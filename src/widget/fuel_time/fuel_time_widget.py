from __future__ import annotations
from decimal import Decimal, ROUND_CEILING
from typing import Any
from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget
from .fuel_time_tracker import FuelTimeData, FuelTimeTracker

class FuelTimeWidget(QWidget):
    geometry_changed=Signal(str,float,float,float,float); selected=Signal(str)
    def __init__(self, widget_id:str, config:dict[str,Any], parent=None)->None:
        super().__init__(parent); self.widget_id=widget_id; self.config=config; self.tracker=FuelTimeTracker(config); self.data=FuelTimeData(); self.edit_mode=False
        self._dragging=self._resizing=False; self._drag_offset=QPoint(); self._start_global=QPoint(); self._start_size=self.size()
        self.setWindowTitle("Sector Flow Drive - Fuel Time"); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True); self.setMouseTracking(True); self.setMinimumSize(300,145); self.update_config(config)
    def update_from_session(self,session:Any)->None: self.data=self.tracker.update(session); self.update()
    def update_config(self,config:dict[str,Any])->None: self.config=config; self.tracker.update_config(config); self.setWindowOpacity(max(.1,min(1.0,float(config.get("opacity",.98))))); self.update()
    def apply_normalized_geometry(self,screen)->None:
        pos,size=self.config.get("position",{}),self.config.get("size",{})
        self.setGeometry(screen.x()+int(screen.width()*float(pos.get("x",.35))),screen.y()+int(screen.height()*float(pos.get("y",.72))),max(self.minimumWidth(),int(screen.width()*float(size.get("width",.30)))),max(self.minimumHeight(),int(screen.height()*float(size.get("height",.16)))))
    def set_edit_mode(self,enabled:bool)->None: self.edit_mode=enabled; self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,not enabled); self.update()
    @staticmethod
    def _v(value:float|None,suffix:str="",decimals:int=1)->str: return "--" if value is None else f"{value:.{decimals}f}{suffix}"
    @staticmethod
    def _fuel_ratio(value:float|None)->str:
        if value is None: return "--"
        rounded=Decimal(str(value)).quantize(Decimal("0.01"),rounding=ROUND_CEILING)
        return f"{rounded:.2f}"
    def paintEvent(self,_event)->None:
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing,True); c=self.config.get("colors",{}); p.setPen(QPen(QColor(c.get("border","#344155")),1.2)); p.setBrush(QColor(c.get("background","#0A0F17EE"))); p.drawRoundedRect(QRectF(1,1,self.width()-2,self.height()-2),10,10)
        margin=max(6,int(min(self.width(),self.height())*.045)); area=self.rect().adjusted(margin,margin,-margin,-margin); title_h=max(22,int(area.height()*.16)); font=p.font(); font.setFamily(str(self.config.get("font_name","Arial"))); font.setBold(True); font.setPixelSize(max(11,int(title_h*.52))); p.setFont(font); p.setPen(QColor(c.get("title","#67E8F9"))); p.drawText(QRectF(area.left()+4,area.top(),area.width()*.55,title_h),Qt.AlignmentFlag.AlignVCenter,"FUEL TIME")
        status = f"{self.data.sample_count}/{int(self.config.get('average_laps',5))} VOLTAS"
        font.setPixelSize(max(8,int(title_h*.38))); font.setBold(False); p.setFont(font); p.setPen(QColor(c.get("muted","#9BA8BA"))); p.drawText(QRectF(area.left()+area.width()*.55,area.top(),area.width()*.45-4,title_h),Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignRight,status)
        p.setPen(QPen(QColor(c.get("accent","#2563EB")),max(1.0,title_h*.07))); p.drawLine(area.left(),area.top()+title_h,area.right(),area.top()+title_h)
        d=self.data; rows=[("COMBUSTIVEL",self._v(d.fuel_l," L"),"MEDIA/VOLTA",self._v(d.fuel_per_lap_l," L")),("VOLTAS REST.",self._v(d.laps_remaining),"AUTONOMIA",self._v(d.fuel_laps," v")),("NECESSARIO",self._v(d.fuel_needed_l," L"),"ADICIONAR",self._v(d.fuel_to_add_l," L")),("ALVO/VOLTA",self._v(d.target_fuel_per_lap_l," L"),"FINAL",self._v(d.finish_fuel_l," L"))]
        if bool(self.config.get("show_energy",True)): rows.append(("ENERGIA/VOLTA",self._v(d.energy_per_lap_pct,"%"),"FUEL RATIO",self._fuel_ratio(d.fuel_ratio)))
        gap=max(3.0,area.width()*.008); y=area.top()+title_h+gap; row_h=max(18,(area.bottom()-y-gap*(len(rows)-1))/max(1,len(rows))); muted=QColor(c.get("muted","#9BA8BA")); text=QColor(c.get("text","#F4F7FB")); panel=QColor(c.get("panel","#151B26"))
        for ll,lv,rl,rv in rows:
            half=(area.width()-gap)/2
            for x,label,value in ((area.left(),ll,lv),(area.left()+half+gap,rl,rv)):
                box=QRectF(x,y,half,row_h); p.setPen(QPen(QColor(c.get("panel_border","#27313E")),1)); p.setBrush(panel); p.drawRoundedRect(box,4,4)
                font.setPixelSize(max(7,int(row_h*.28))); font.setBold(False); p.setFont(font); p.setPen(muted); p.drawText(box.adjusted(max(5,row_h*.18),0,-box.width()*.46,0),Qt.AlignmentFlag.AlignVCenter,label)
                font.setPixelSize(max(9,int(row_h*.43))); font.setBold(True); p.setFont(font); value_color=text
                if label in {"ADICIONAR","FINAL"} and value != "--":
                    numeric = d.fuel_to_add_l if label == "ADICIONAR" else d.finish_fuel_l
                    if numeric is not None and numeric < 0.05: value_color=QColor(c.get("good","#16C784"))
                    if numeric is not None and numeric < 0: value_color=QColor(c.get("warning","#EF4444"))
                p.setPen(value_color); p.drawText(box.adjusted(box.width()*.50,0,-max(5,row_h*.18),0),Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignRight,value)
            y+=row_h+gap
        if self.edit_mode: p.setPen(QPen(QColor(c.get("edit_border","#8B5CF6")),2,Qt.PenStyle.DashLine)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRect(self.rect().adjusted(1,1,-2,-2)); p.fillRect(self.width()-14,self.height()-14,14,14,QColor(c.get("edit_border","#8B5CF6")))
    def mousePressEvent(self,e:QMouseEvent)->None:
        if self.edit_mode and e.button()==Qt.MouseButton.LeftButton:
            self.selected.emit(self.widget_id); self._resizing=e.position().x()>=self.width()-18 and e.position().y()>=self.height()-18; self._dragging=not self._resizing; self._start_global=e.globalPosition().toPoint(); self._start_size=self.size(); self._drag_offset=e.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def mouseMoveEvent(self,e:QMouseEvent)->None:
        if self._resizing:
            d=e.globalPosition().toPoint()-self._start_global; self.resize(max(self.minimumWidth(),self._start_size.width()+d.x()),max(self.minimumHeight(),self._start_size.height()+d.y())); self.update()
        elif self._dragging: self.move(e.globalPosition().toPoint()-self._drag_offset)
    def mouseReleaseEvent(self,e:QMouseEvent)->None:
        if (self._dragging or self._resizing) and e.button()==Qt.MouseButton.LeftButton:
            self._dragging=self._resizing=False; s=self.screen().geometry(); self.geometry_changed.emit(self.widget_id,(self.x()-s.x())/s.width(),(self.y()-s.y())/s.height(),self.width()/s.width(),self.height()/s.height())
