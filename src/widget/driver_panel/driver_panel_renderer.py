from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
from typing import Any, Sequence
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen


@dataclass(slots=True)
class DriverPanelViewData:
    speed_kmh: float = 0.0
    rpm: float = 0.0
    max_rpm: float = 9000.0
    gear: int = 0
    throttle: float = 0.0
    brake: float = 0.0
    clutch: float = 0.0
    steering: float = 0.0
    max_rpm_seen: float = 0.0
    max_throttle_seen: float = 0.0
    max_brake_seen: float = 0.0
    max_clutch_seen: float = 0.0
    throttle_abrupt: bool = False
    brake_abrupt: bool = False
    gear_flash: bool = False


class DriverPanelRenderer:
    """Novo visual inspirado na referência; não conhece a fonte da telemetria."""

    def draw(self, p: QPainter, bounds: QRectF, data: DriverPanelViewData,
             throttle_history: Sequence[float], brake_history: Sequence[float],
             clutch_history: Sequence[float], rpm_history: Sequence[float],
             steering_history: Sequence[float], speed_history: Sequence[float],
             config: dict[str, Any], edit_mode: bool = False) -> None:
        p.save(); p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        c=config.get("colors",{}); bg=QColor(c.get("background","#05080C")); bg.setAlphaF(float(config.get("background_opacity",.92)))
        panel=QColor(c.get("panel","#071014")); border=QColor(c.get("border","#18333A")); text=QColor(c.get("text","#F4F8FA")); muted=QColor(c.get("muted","#8CA0A8"))
        colors={"rpm":QColor(c.get("rpm_graph","#FFD21F")),"throttle":QColor(c.get("throttle","#18E65A")),"brake":QColor(c.get("brake","#FF2638")),"clutch":QColor(c.get("clutch","#278BFF")),"steering":QColor(c.get("steering_graph","#C783FF")),"speed":QColor(c.get("speed","#20D4E8"))}
        s=max(.30,min(2.5,min(bounds.width()/1600,bounds.height()/650))); radius=max(5,float(config.get("border_radius",14))*s)
        p.setPen(QPen(border,max(1,2*s))); p.setBrush(bg); p.drawRoundedRect(bounds.adjusted(1,1,-1,-1),radius,radius)
        content=bounds.adjusted(max(7,16*s),max(7,16*s),-max(7,16*s),-max(7,16*s)); e=config.get("elements",{}); show=lambda k:bool(e.get(k,True))
        wheel_w=content.width()*(.23 if show("steering") or show("gear") or show("speed") else 0)
        pedal_flags=config.get("pedal_elements",{})
        pedal_count=sum(bool(pedal_flags.get(key,True)) for key in ("brake","throttle","clutch")) if show("pedals") else 0
        pedal_gap=max(3.0,float(config.get("pedal_bar_gap",9.0))*s)
        pedal_bar_width=max(4.0,float(config.get("pedal_bar_width",38.0))*s)
        pedals_w=(pedal_count*pedal_bar_width+(pedal_count+1)*pedal_gap) if pedal_count else 0
        pedals_w=min(content.width()*.30,pedals_w)
        rpm_h=content.height()*(.21 if show("rpm") else 0)
        column_gap=8*s
        rpm_w=content.width()-wheel_w-pedals_w-column_gap*2
        rpm_rect=QRectF(content.left(),content.top(),max(0,rpm_w),rpm_h)
        body=QRectF(content.left(),rpm_rect.bottom()+(8*s if rpm_h else 0),content.width(),content.height()-rpm_h-(8*s if rpm_h else 0))
        if show("rpm"): self._rpm(p,rpm_rect,data,config,text,muted,panel,s)
        gap=8*s
        graph=QRectF(body.left(),body.top(),max(0,body.width()-wheel_w-pedals_w-gap*2),body.height())
        pedals=QRectF(graph.right()+gap,content.top(),pedals_w,content.height())
        wheel=QRectF(pedals.right()+gap,content.top(),wheel_w,content.height())
        if show("graph"): self._graph(p,graph,{"throttle":throttle_history,"brake":brake_history,"clutch":clutch_history},colors,text,muted,panel,border,config,s)
        if show("pedals"): self._pedals(p,pedals,data,colors,text,muted,panel,border,config,s)
        if wheel_w: self._wheel(p,wheel,data,colors,text,panel,border,config,s)
        if edit_mode:
            pen=QPen(QColor(c.get("edit_border","#8B5CF6")),max(1.5,2.5*s)); pen.setStyle(Qt.PenStyle.DashLine); p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush); p.drawRoundedRect(bounds.adjusted(3,3,-3,-3),radius,radius)
        p.restore()

    def _rpm(self,p:QPainter,r:QRectF,d:DriverPanelViewData,cfg:dict[str,Any],text:QColor,muted:QColor,panel:QColor,s:float)->None:
        ratio=max(0,min(1,d.rpm/max(1,d.max_rpm))); shift=float(cfg.get("layout",{}).get("shift_start",.78)); red=float(cfg.get("layout",{}).get("red_start",.92)); active=QColor("#21D760") if ratio<shift else QColor("#FFD21F") if ratio<red else QColor("#FF2638")
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(panel); p.drawRoundedRect(r,8*s,8*s); fill=QRectF(r.left(),r.top(),r.width()*ratio,r.height()); fc=QColor(active); fc.setAlpha(92); p.setBrush(fc); p.drawRoundedRect(fill,8*s,8*s)
        x=r.left()+r.width()*red; p.setPen(QPen(QColor("#FF5B30"),max(2,3*s))); p.drawLine(QPointF(x,r.top()),QPointF(x,r.bottom()))
        value=f"{d.rpm:,.0f}".replace(",","."); p.setFont(self._fit(cfg,r,value,r.height()*.68,12,True)); p.setPen(text); p.drawText(r,Qt.AlignmentFlag.AlignCenter,value)

    def _graph(self,p:QPainter,r:QRectF,series:dict[str,Sequence[float]],colors:dict[str,QColor],text:QColor,muted:QColor,panel:QColor,border:QColor,cfg:dict[str,Any],s:float)->None:
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(panel); p.drawRoundedRect(r,8*s,8*s); graph=r.adjusted(8*s,8*s,-8*s,-8*s)
        enabled=cfg.get("pedal_elements",{})
        p.save(); p.setClipRect(graph)
        for name,values in series.items():
            if bool(enabled.get(name,True)): self._path(p,graph,values,colors[name],max(1.3,2.5*s))
        p.restore()

    @staticmethod
    def _path(p:QPainter,r:QRectF,values:Sequence[float],color:QColor,width:float)->None:
        if len(values)<2:return
        path=QPainterPath()
        for i,raw in enumerate(values):
            if isinstance(raw,(tuple,list)) and len(raw)>=2:
                x_ratio=float(raw[0]); value=float(raw[1])
            else:
                x_ratio=i/(len(values)-1); value=float(raw)
            point=QPointF(r.left()+r.width()*x_ratio,r.bottom()-r.height()*max(0,min(1,value))); path.moveTo(point) if i==0 else path.lineTo(point)
        pen=QPen(color,width); pen.setCapStyle(Qt.PenCapStyle.RoundCap); pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin); p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush); p.drawPath(path)

    def _pedals(self,p:QPainter,r:QRectF,d:DriverPanelViewData,colors:dict[str,QColor],text:QColor,muted:QColor,panel:QColor,border:QColor,cfg:dict[str,Any],s:float)->None:
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(panel); p.drawRoundedRect(r,8*s,8*s); pe=cfg.get("pedal_elements",{}); items=[("",d.brake,d.max_brake_seen,"brake",d.brake_abrupt),("",d.throttle,d.max_throttle_seen,"throttle",d.throttle_abrupt),("",d.clutch,d.max_clutch_seen,"clutch",False)]; items=[i for i in items if bool(pe.get(i[3],True))]
        if not items:return
        gap=max(3.0,float(cfg.get("pedal_bar_gap",9.0))*s)
        bw=min(
            max(4.0,float(cfg.get("pedal_bar_width",38.0))*s),
            max(4.0,(r.width()-gap*(len(items)+1))/len(items)),
        )
        group_width=len(items)*bw+(len(items)-1)*gap
        start_x=r.center().x()-group_width/2
        value_h=max(24*s,r.height()*.17); top=r.top()+value_h; bottom=r.bottom()-8*s
        for i,(label,value,maximum,key,alert) in enumerate(items):
            x=start_x+i*(bw+gap); bar=QRectF(x,top,bw,bottom-top)
            percent=f"{value*100:.0f}%"; percent_rect=QRectF(x,r.top()+4*s,bw,value_h-6*s)
            p.setFont(self._fit(cfg,percent_rect,percent,max(12*s,value_h*.42),8,True)); p.setPen(colors[key]); p.drawText(percent_rect,Qt.AlignmentFlag.AlignCenter,percent)
            p.setPen(QPen(colors[key].darker(160),max(1,s))); p.setBrush(QColor("#071B20")); p.drawRoundedRect(bar,4*s,4*s); fill=QRectF(bar.left(),bar.bottom()-bar.height()*value,bar.width(),bar.height()*value); p.setBrush(colors[key]); p.drawRoundedRect(fill,4*s,4*s)

    def _wheel(self,p:QPainter,r:QRectF,d:DriverPanelViewData,colors:dict[str,QColor],text:QColor,panel:QColor,border:QColor,cfg:dict[str,Any],s:float)->None:
        wheel_scale=max(.35,min(2.0,float(cfg.get("steering_size_scale",1.0))))
        base_radius=max(8,min(r.width()*.378,r.height()*.243))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(panel); p.drawRoundedRect(r,8*s,8*s); e=cfg.get("elements",{}); center=QPointF(r.center().x(),r.top()+r.height()*.34); radius=base_radius*wheel_scale; max_deg=float(cfg.get("steering_visual_degrees",540)); angle=d.steering*max_deg
        if bool(e.get("steering",True)):
            marker_visible=bool(e.get("steering_marker",True))
            dynamic=QColor(cfg.get("colors",{}).get("steering_marker","#FFD21F")); style=str(cfg.get("steering_style","Circular"))
            if style!="Somente ângulo":
                p.save(); p.translate(center); custom=str(cfg.get("custom_wheel_image","")).strip()
                if style=="Imagem personalizada" and custom and Path(custom).is_file():
                    p.rotate(angle); p.drawImage(QRectF(-radius,-radius,radius*2,radius*2),QImage(custom))
                    if marker_visible:
                        p.setPen(Qt.PenStyle.NoPen); p.setBrush(dynamic); p.drawEllipse(QPointF(0,-radius),max(4,radius*.105),max(4,radius*.105))
                else:
                    p.setPen(QPen(QColor(cfg.get("colors",{}).get("wheel","#0B4A50")),max(5,radius*.14))); p.setBrush(Qt.BrushStyle.NoBrush)
                    if style=="GT":p.drawRoundedRect(QRectF(-radius,-radius*.78,radius*2,radius*1.56),radius*.28,radius*.28)
                    elif style=="Fórmula":p.drawRoundedRect(QRectF(-radius,-radius*.62,radius*2,radius*1.24),radius*.16,radius*.16)
                    else:p.drawEllipse(QPointF(0,0),radius,radius)
                    if marker_visible:
                        marker_angle=angle*3.141592653589793/180.0; marker=QPointF(radius*math.sin(marker_angle),-radius*math.cos(marker_angle)); p.setPen(Qt.PenStyle.NoPen); p.setBrush(dynamic); p.drawEllipse(marker,max(4,radius*.105),max(4,radius*.105))
                p.restore()
        ratio=d.rpm/max(1,d.max_rpm); gear_color=QColor("#FFFFFF") if d.gear_flash else QColor("#FF334D") if ratio>=float(cfg.get("layout",{}).get("red_start",.92)) else QColor("#FFD21F")
        if bool(e.get("gear",True)):
            gear_scale=max(.35,min(3.0,float(cfg.get("gear_font_scale",1.0))))
            gear=self._format_gear(d.gear); box=QRectF(r.left(),center.y()+radius*1.12,r.width(),max(base_radius*1.02,42*s*gear_scale)); p.setFont(self._fit(cfg,box,gear,base_radius*.912*gear_scale,8,True)); p.setPen(gear_color); p.drawText(box,Qt.AlignmentFlag.AlignCenter,gear)
        if bool(e.get("speed",True)):
            speed_scale=max(.35,min(3.0,float(cfg.get("speed_font_scale",1.0))))
            unit=str(cfg.get("speed_unit","km/h")); value=d.speed_kmh*.621371 if unit=="mph" else d.speed_kmh; speed_text=f"{value:.0f}"
            if str(cfg.get("speed_position","inside")) == "beside_gear":
                box=QRectF(center.x()+radius*.38,center.y()+radius*1.12,max(1,r.right()-center.x()-radius*.38),radius*1.02); p.setFont(self._fit(cfg,box,speed_text,base_radius*.588*speed_scale,7,True)); p.setPen(text); p.drawText(box,Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,speed_text)
            else:
                box=QRectF(center.x()-radius*.90,center.y()-radius*.52,radius*1.80,radius*1.04); p.setFont(self._fit(cfg,box,speed_text,base_radius*.588*speed_scale,7,True)); p.setPen(text); p.drawText(box,Qt.AlignmentFlag.AlignCenter,speed_text)

    @staticmethod
    def _font(cfg:dict[str,Any],px:float,bold:bool=False)->QFont:
        f=QFont(str(cfg.get("font",{}).get("family","Arial"))); f.setPixelSize(max(7,int(px))); f.setBold(bold); return f
    def _fit(self,cfg:dict[str,Any],r:QRectF,value:str,preferred:float,minimum:float,bold:bool=False)->QFont:
        size=max(minimum,preferred)
        while size>minimum:
            f=self._font(cfg,size,bold)
            if QFontMetricsF(f).horizontalAdvance(value)<=r.width()*.88:return f
            size-=1
        return self._font(cfg,minimum,bold)
    @staticmethod
    def _format_gear(gear:int)->str:return "R" if gear<0 else "N" if gear==0 else str(gear)
