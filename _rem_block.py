        with col_rem:
            try:
                from pdf_helper import generar_remision as _gen_rem
                _lineas_rem = [{"producto": l["producto"],
                                "unidad":   l.get("unidad",""),
                                "cantidad": float(l.get("cantidad") or 0),
                                "total":    round(float(l.get("precio") or 0)
                                                  * float(l.get("cantidad") or 0), 2)}
                               for l in lineas_pdf]
                _fecha_rem  = fecha_ped.strftime("%d/%m/%Y")
                _rem_bytes  = _gen_rem(l0["cliente"], _lineas_rem,
                                       int(l0["semana"]), int(l0["año"]),
                                       _fecha_rem)
                _b64_rem    = base64.b64encode(_rem_bytes).decode()
                _fn_id      = ("remfn_" + sufijo + "_" + str(unico)
                               ).replace("-","_").replace(".","_")
                _btn_style  = ("background:#555;color:white;border:none;"
                               "border-radius:6px;padding:6px 10px;"
                               "font-size:13px;cursor:pointer;width:100%;"
                               "font-family:sans-serif")
                _html_parts = [
                    "<script>",
                    "function ", _fn_id, "(){",
                    "var b=atob('", _b64_rem, "');",
                    "var a=new Uint8Array(b.length);",
                    "for(var i=0;i<b.length;i++)a[i]=b.charCodeAt(i);",
                    "var blob=new Blob([a],{type:'application/pdf'});",
                    "var u=URL.createObjectURL(blob);",
                    "var w=window.open(u,'_blank');",
                    "if(w){setTimeout(function(){try{w.print();}catch(e){}},1500);}",
                    "}",
                    "</script>",
                    "<button onclick='", _fn_id, "()' style='", _btn_style, "'>",
                    "\U0001f5a8 Remisi\u00f3n</button>",
                ]
                components.html("".join(_html_parts), height=40)
            except Exception as _e:
                col_rem.caption("Rem: " + str(_e))
