import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3, json, os, io
from datetime import datetime

st.set_page_config(page_title="WFI Monitoring Dashboard", page_icon="💧", layout="wide")
DB_PATH = "wfi_monitoring.db"
INITIAL_JSON = "wfi_initial_data.json"

FIELDS = {
    "conductivity": "Conductivity",
    "ph": "pH",
    "toc": "TOC",
    "microbial": "Microbial Control",
}
NUMERIC = list(FIELDS.keys())

def connect():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    con=connect()
    con.execute('''CREATE TABLE IF NOT EXISTS records (
      id INTEGER PRIMARY KEY AUTOINCREMENT, point TEXT NOT NULL, date TEXT NOT NULL,
      conductivity REAL, ph REAL, toc REAL, microbial REAL, nitrate TEXT, endotoxin TEXT, appearance TEXT,
      conductivity_spec REAL, conductivity_action REAL, conductivity_alert REAL,
      ph_upper_spec REAL, ph_upper_action REAL, ph_upper_alert REAL,
      ph_lower_spec REAL, ph_lower_action REAL, ph_lower_alert REAL,
      toc_spec REAL, toc_action REAL, toc_alert REAL,
      microbial_spec REAL, microbial_action REAL, microbial_alert REAL, nitrate_limit REAL, source TEXT,
      created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(point,date));''')
    con.commit()
    count=con.execute('SELECT COUNT(*) FROM records').fetchone()[0]
    if count==0 and os.path.exists(INITIAL_JSON):
        with open(INITIAL_JSON,encoding='utf8') as f: data=json.load(f)
        for x in data:
            try: insert_record(con,x,ignore=True)
            except Exception: pass
        con.commit()
    con.close()

def insert_record(con, x, ignore=False):
    cols=['point','date','conductivity','ph','toc','microbial','nitrate','endotoxin','appearance',
      'conductivity_spec','conductivity_action','conductivity_alert','ph_upper_spec','ph_upper_action','ph_upper_alert',
      'ph_lower_spec','ph_lower_action','ph_lower_alert','toc_spec','toc_action','toc_alert','microbial_spec','microbial_action','microbial_alert','nitrate_limit','source']
    sql='INSERT OR IGNORE' if ignore else 'INSERT'
    con.execute(f"{sql} INTO records ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",[x.get(c) for c in cols])

def load_data():
    con=connect(); df=pd.read_sql_query('SELECT * FROM records ORDER BY date, point',con); con.close()
    if not df.empty:
        df['date_dt']=pd.to_datetime(df['date'],dayfirst=True,errors='coerce')
    return df

def clean_num(v):
    if v is None or v=="": return None
    return float(v)

init_db()
st.markdown('''<style>
.block-container{padding-top:1.4rem;padding-bottom:2rem;max-width:1600px}
[data-testid="stMetric"]{background:#f4f7fb;border:1px solid #e1e8f0;padding:14px 18px;border-radius:12px}
div[data-testid="stForm"]{border:1px solid #e1e8f0;border-radius:12px;padding:18px}
</style>''',unsafe_allow_html=True)
st.title("💧 WFI Monitoring Dashboard")
st.caption("Water for Injection · Monitoring, trending and data entry · Internal operational tool")

with st.sidebar:
    st.header("Navigation")
    page=st.radio("Choose view",["Dashboard","Enter results","Records & corrections","Import / export"])
    st.divider()
    st.caption("GMP note: this prototype is not a validated computerized system. Review access control, audit trail, backup, validation and SOP requirements before GMP use.")

df=load_data()
if page=="Dashboard":
    st.subheader("Monitoring overview")
    if df.empty:
        st.info("No records yet. Add results from Enter results or import a workbook.")
    else:
        points=sorted(df['point'].dropna().unique().tolist())
        c1,c2,c3=st.columns([1.3,1,1])
        with c1: selected_points=st.multiselect("Sampling point",points,default=points)
        with c2:
            min_date=df['date_dt'].min().date() if df['date_dt'].notna().any() else None
            max_date=df['date_dt'].max().date() if df['date_dt'].notna().any() else None
            date_range=st.date_input("Date range",value=(min_date,max_date) if min_date and max_date else ())
        with c3: metric=st.selectbox("Trend parameter",list(FIELDS),format_func=lambda x:FIELDS[x])
        view=df[df['point'].isin(selected_points)].copy()
        if isinstance(date_range,tuple) and len(date_range)==2:
            view=view[(view['date_dt'].dt.date>=date_range[0])&(view['date_dt'].dt.date<=date_range[1])]
        valid=view[view[metric].notna()]
        total=len(view)
        # Screening is based on alert/action/spec columns from the source workbook; does not replace QA review.
        def status(row, key):
            v=row.get(key)
            if pd.isna(v): return 'No result'
            if key=='conductivity':
                if pd.notna(row.get('conductivity_spec')) and v>row['conductivity_spec']: return 'Above spec'
                if pd.notna(row.get('conductivity_alert')) and v>row['conductivity_alert']: return 'Alert/action range'
            elif key=='ph':
                if pd.notna(row.get('ph_upper_spec')) and v>row['ph_upper_spec']: return 'Above spec'
                if pd.notna(row.get('ph_lower_spec')) and v<row['ph_lower_spec']: return 'Below spec'
                if pd.notna(row.get('ph_upper_alert')) and v>row['ph_upper_alert']: return 'Upper alert range'
                if pd.notna(row.get('ph_lower_alert')) and v<row['ph_lower_alert']: return 'Lower alert range'
            elif key=='toc':
                if pd.notna(row.get('toc_spec')) and v>row['toc_spec']: return 'Above spec'
                if pd.notna(row.get('toc_alert')) and v>row['toc_alert']: return 'Alert/action range'
            elif key=='microbial':
                if pd.notna(row.get('microbial_spec')) and v>row['microbial_spec']: return 'Above spec'
                if pd.notna(row.get('microbial_alert')) and v>row['microbial_alert']: return 'Alert/action range'
            return 'Review limits'
        # Cards are screening indicators only; don't imply a batch disposition.
        latest=valid.sort_values('date_dt')
        k1,k2,k3,k4=st.columns(4)
        k1.metric("Records in view",f"{total:,}")
        k2.metric("Results for selected parameter",f"{len(valid):,}")
        k3.metric("Sampling points",f"{view['point'].nunique()}")
        k4.metric("Latest result",f"{latest.iloc[-1][metric]:g}" if len(latest) else "—")
        st.divider()
        left,right=st.columns([1.6,1])
        with left:
            st.markdown(f"#### {FIELDS[metric]} trend")
            if len(valid):
                fig=px.line(valid.sort_values('date_dt'),x='date_dt',y=metric,color='point',markers=True,
                            labels={'date_dt':'Date',metric:FIELDS[metric],'point':'Sampling point'},template='plotly_white')
                # Display spec/action/alert reference lines only where consistent across selected records.
                limits={'conductivity':[('conductivity_spec','Spec'),('conductivity_action','Action'),('conductivity_alert','Alert')],
                        'ph':[('ph_upper_spec','Upper spec'),('ph_upper_alert','Upper alert'),('ph_lower_spec','Lower spec'),('ph_lower_alert','Lower alert')],
                        'toc':[('toc_spec','Spec'),('toc_action','Action'),('toc_alert','Alert')],
                        'microbial':[('microbial_spec','Spec'),('microbial_action','Action'),('microbial_alert','Alert')]}
                for col,label in limits[metric]:
                    vals=view[col].dropna().unique() if col in view else []
                    if len(vals)==1:
                        fig.add_hline(y=float(vals[0]),line_dash='dash',annotation_text=label,annotation_position='top left')
                fig.update_layout(legend_title_text='Sampling point',hovermode='x unified')
                st.plotly_chart(fig,use_container_width=True)
            else: st.info("No numeric results for this selection.")
        with right:
            st.markdown("#### Results by sampling point")
            if len(valid):
                agg=valid.groupby('point')[metric].agg(['count','mean','min','max']).reset_index()
                agg.columns=['Sampling point','N','Mean','Min','Max']
                st.dataframe(agg.round(4),use_container_width=True,hide_index=True)
                fig2=px.box(valid,x='point',y=metric,color='point',points='outliers',template='plotly_white',labels={'point':'Sampling point',metric:FIELDS[metric]})
                fig2.update_layout(showlegend=False,xaxis_tickangle=-45)
                st.plotly_chart(fig2,use_container_width=True)
        st.markdown("#### Qualitative results")
        q1,q2,q3=st.columns(3)
        with q1:
            st.caption("Nitrate")
            st.dataframe(view.groupby('nitrate',dropna=False).size().rename('Count').reset_index(),use_container_width=True,hide_index=True)
        with q2:
            st.caption("Endotoxin")
            st.dataframe(view.groupby('endotoxin',dropna=False).size().rename('Count').reset_index(),use_container_width=True,hide_index=True)
        with q3:
            st.caption("Appearance")
            st.dataframe(view.groupby('appearance',dropna=False).size().rename('Count').reset_index(),use_container_width=True,hide_index=True)
        st.markdown("#### Filtered data")
        cols=['date','point','conductivity','ph','toc','microbial','nitrate','endotoxin','appearance']
        st.dataframe(view[cols].sort_values(['date','point'],ascending=[False,True]),use_container_width=True,hide_index=True)

elif page=="Enter results":
    st.subheader("Enter a monitoring result")
    st.write("Enter one sample point and sampling date per record. Empty fields remain blank; they are not converted to zero.")
    known=sorted(df['point'].dropna().unique().tolist()) if not df.empty else []
    with st.form('entry_form',clear_on_submit=True):
        a,b,c=st.columns(3)
        with a:
            point_mode=st.radio("Sampling point",["Existing point","New point"],horizontal=True)
            if point_mode=="Existing point" and known: point=st.selectbox("Select point",known)
            else: point=st.text_input("New sampling point ID",placeholder="e.g. PR-11-WFI-03")
            sample_date=st.date_input("Sampling date",value=datetime.today().date())
        with b:
            conductivity=st.number_input("Conductivity",min_value=0.0,value=None,step=0.01,format="%.4f",placeholder="Leave blank if not tested")
            ph=st.number_input("pH",min_value=0.0,max_value=14.0,value=None,step=0.01,format="%.3f",placeholder="Leave blank if not tested")
            toc=st.number_input("TOC",min_value=0.0,value=None,step=0.001,format="%.4f",placeholder="Leave blank if not tested")
            microbial=st.number_input("Microbial Control (CFU)",min_value=0.0,value=None,step=1.0,format="%.0f",placeholder="Leave blank if not tested")
        with c:
            nitrate=st.selectbox("Nitrate result",["", "Pass", "Fail", "Not tested"])
            endotoxin=st.selectbox("Endotoxin result",["", "Pass", "Fail", "Not tested"])
            appearance=st.selectbox("Appearance",["", "Clear & Colorless", "Fail / atypical", "Not tested"])
            st.caption("Limits are populated from the default workbook template. Confirm current approved limits before use.")
        st.markdown("**Optional limit overrides** (only complete these if approved limits differ for this point)")
        l1,l2,l3,l4=st.columns(4)
        with l1: cond_spec=st.number_input("Conductivity spec",min_value=0.0,value=1.3,step=0.01)
        with l2: ph_upper=st.number_input("pH upper spec",min_value=0.0,max_value=14.0,value=7.0,step=0.1); ph_lower=st.number_input("pH lower spec",min_value=0.0,max_value=14.0,value=5.0,step=0.1)
        with l3: toc_spec=st.number_input("TOC spec",min_value=0.0,value=0.5,step=0.01)
        with l4: micro_spec=st.number_input("Microbial spec",min_value=0.0,value=10.0,step=1.0)
        submitted=st.form_submit_button("Save monitoring result",type="primary",use_container_width=True)
    if submitted:
        if not point or not point.strip(): st.error("Sampling point is required.")
        else:
            x={'point':point.strip(),'date':sample_date.strftime('%d.%m.%Y'),'conductivity':conductivity,'ph':ph,'toc':toc,'microbial':microbial,
               'nitrate':nitrate if nitrate not in ('','Not tested') else '', 'endotoxin':endotoxin if endotoxin not in ('','Not tested') else '',
               'appearance':appearance if appearance not in ('','Not tested') else '', 'conductivity_spec':cond_spec,'conductivity_action':1.3,'conductivity_alert':1.26,
               'ph_upper_spec':ph_upper,'ph_upper_action':7,'ph_upper_alert':6.67,'ph_lower_spec':ph_lower,'ph_lower_action':5.11,'ph_lower_alert':5.42,
               'toc_spec':toc_spec,'toc_action':0.23,'toc_alert':0.183,'microbial_spec':micro_spec,'microbial_action':10,'microbial_alert':5,
               'nitrate_limit':0.2,'source':'Manual entry'}
            con=connect()
            try:
                insert_record(con,x); con.commit(); st.success("Record saved.")
            except sqlite3.IntegrityError: st.error("A record for this sampling point and date already exists. Use Records & corrections to review it.")
            finally: con.close()

elif page=="Records & corrections":
    st.subheader("Records and corrections")
    if df.empty: st.info("No records available.")
    else:
        pts=['All']+sorted(df['point'].dropna().unique().tolist())
        sel=st.selectbox("Sampling point filter",pts)
        show=df if sel=='All' else df[df['point']==sel]
        st.dataframe(show[['id','date','point','conductivity','ph','toc','microbial','nitrate','endotoxin','appearance','source']].sort_values('date',ascending=False),use_container_width=True,hide_index=True)
        st.warning("For traceability, production use should have controlled corrections and a permanent audit trail. This prototype only provides basic record editing/deletion.")
        ids=show['id'].astype(int).tolist()
        rid=st.selectbox("Record ID to edit or delete",ids,format_func=lambda i:f"ID {i} · {show.loc[show.id==i,'point'].iloc[0]} · {show.loc[show.id==i,'date'].iloc[0]}")
        rec=show[show.id==rid].iloc[0]
        with st.form('edit_form'):
            e1,e2,e3=st.columns(3)
            with e1: epoint=st.text_input("Sampling point",value=str(rec['point'])); edate=st.text_input("Date (DD.MM.YYYY)",value=str(rec['date']))
            with e2:
                ec=st.text_input("Conductivity",value='' if pd.isna(rec['conductivity']) else str(rec['conductivity']))
                eph=st.text_input("pH",value='' if pd.isna(rec['ph']) else str(rec['ph']))
                etoc=st.text_input("TOC",value='' if pd.isna(rec['toc']) else str(rec['toc']))
                emic=st.text_input("Microbial Control",value='' if pd.isna(rec['microbial']) else str(rec['microbial']))
            with e3: enit=st.text_input("Nitrate",value=str(rec['nitrate'] or '')); een=st.text_input("Endotoxin",value=str(rec['endotoxin'] or '')); eapp=st.text_input("Appearance",value=str(rec['appearance'] or ''))
            save=st.form_submit_button("Save changes")
        if save:
            try:
                con=connect(); con.execute('UPDATE records SET point=?,date=?,conductivity=?,ph=?,toc=?,microbial=?,nitrate=?,endotoxin=?,appearance=?,source=? WHERE id=?',
                 (epoint.strip(),edate.strip(),clean_num(ec),clean_num(eph),clean_num(etoc),clean_num(emic),enit,een,eapp,'Edited in dashboard',int(rid))); con.commit(); con.close(); st.success("Changes saved. Refresh the page to view updated values.")
            except Exception as e: st.error(f"Could not save changes: {e}")
        if st.button("Delete selected record",type="secondary"):
            con=connect(); con.execute('DELETE FROM records WHERE id=?',(int(rid),)); con.commit(); con.close(); st.success("Record deleted. Refresh the page.")

else:
    st.subheader("Import and export")
    st.markdown("#### Import an Excel monitoring workbook")
    up=st.file_uploader("Upload .xlsx file",type=['xlsx'])
    if up and st.button("Import workbook",type="primary"):
        try:
            import openpyxl, tempfile
            wb=openpyxl.load_workbook(up,data_only=True)
            imported=0; con=connect()
            for ws in wb.worksheets:
                if ws.max_row<8 or not ws.cell(5,1).value: continue
                point=str(ws.cell(5,1).value).strip()
                for r in range(8,ws.max_row+1):
                    date=ws.cell(r,1).value
                    if not date: continue
                    def n(c):
                        v=ws.cell(r,c).value
                        try: return float(v) if v is not None else None
                        except: return None
                    x={'point':point,'date':str(date),'conductivity':n(2),'ph':n(6),'toc':n(13),'microbial':n(17),
                       'nitrate':str(ws.cell(r,21).value or ''),'endotoxin':str(ws.cell(r,23).value or ''),'appearance':str(ws.cell(r,24).value or ''),
                       'conductivity_spec':n(3),'conductivity_action':n(4),'conductivity_alert':n(5),'ph_upper_spec':n(7),'ph_upper_action':n(8),'ph_upper_alert':n(9),
                       'ph_lower_spec':n(10),'ph_lower_action':n(11),'ph_lower_alert':n(12),'toc_spec':n(14),'toc_action':n(15),'toc_alert':n(16),
                       'microbial_spec':n(18),'microbial_action':n(19),'microbial_alert':n(20),'nitrate_limit':n(22),'source':'Imported workbook'}
                    before=con.total_changes; insert_record(con,x,ignore=True); imported += con.total_changes-before
            con.commit(); con.close(); st.success(f"Import finished. {imported} new records added; duplicates skipped.")
        except Exception as e: st.error(f"Import failed: {e}")
    st.divider()
    st.markdown("#### Export")
    if not df.empty:
        export=df.drop(columns=['date_dt'],errors='ignore')
        st.download_button("Download all records as CSV",export.to_csv(index=False).encode('utf-8-sig'),file_name='wfi_monitoring_export.csv',mime='text/csv',use_container_width=True)
        excel_buffer=io.BytesIO()
        export.to_excel(excel_buffer,index=False,engine='openpyxl')
        st.download_button("Download all records as Excel",excel_buffer.getvalue(),file_name='wfi_monitoring_export.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True)
    else: st.info("No records to export yet.")

st.divider()
st.caption("Screening charts are decision-support only. Always evaluate results against the current approved specification, alert/action limits, method, and applicable SOP; do not use this prototype alone for batch or water-system disposition.")
