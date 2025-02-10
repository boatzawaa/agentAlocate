from flask import Flask, request, jsonify
from flask_mysqldb import MySQL
from flask_cors import CORS
import config
import random
from datetime import datetime

app = Flask(__name__)
CORS(app)  # อนุญาตให้เรียก API จากโดเมนอื่นได้

# ตั้งค่าการเชื่อมต่อ MySQL
app.config["MYSQL_HOST"] = config.MYSQL_HOST
app.config["MYSQL_USER"] = config.MYSQL_USER
app.config["MYSQL_PASSWORD"] = config.MYSQL_PASSWORD
app.config["MYSQL_DB"] = config.MYSQL_DB
app.config["MYSQL_PORT"] = config.MYSQL_PORT
app.config["MYSQL_CURSORCLASS"] = config.MYSQL_CURSORCLASS

mysql = MySQL(app)

# API เพื่อดึงข้อมูลทั้งหมดจากตาราง users
@app.route("/", methods=["GET"])
def get_users():
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM DigitalOrdLotTB where LotDate=20221101")
    users = cur.fetchall()
    cur.close()
    return jsonify(users)

@app.route("/prepareAgentInfo", methods=["POST"])
def Prepare_Agent_Info():       
    start_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]     
    print(start_datetime)
    # time.sleep(5)
    data = request.get_json()
    # การตรวจสอบข้อมูล
    if not data.get('LotDate') or not data.get('userName'):
        return jsonify({'response': {'status':'error','messege':'LotDate and userName are required'}}), 400    
    LotDate = data.get("LotDate")
    userName = data.get("userName")
    action = "prepareAgentInfo"
    print(userName, " : ",LotDate)
     
    # select บุคคลทั่วไป ##################################################################
    cur = mysql.connection.cursor()
    try:
        cur.execute(f"SELECT Nums, LotDate, IDCard, Agent_Type FROM DigitalOrdLotTB WHERE LotDate={LotDate} AND Agent_Type='บุคคลทั่วไป'")
        generalMem = cur.fetchall()
    except Exception as e:
        return jsonify({'response': {'status':'error','messege': f'Database query error: {str(e)}'}}), 500
    finally:
        cur.close()

    # ถ้าไม่พบข้อมูล
    if len(generalMem) == 0:
        return jsonify({'response': {'status':'error','messege': 'data from FROM DigitalOrdLotTB not found'}}), 404
    
    # select สมาคม #############################################################
    cur = mysql.connection.cursor()
    try:
        cur.execute(f"SELECT LotDate, IDCard, Agent_Type FROM DigitalOrdLotTB WHERE LotDate={LotDate} AND Agent_Type='สมาคม'")
        association = cur.fetchall()
    except Exception as e:
        return jsonify({'response': {'status':'error','messege': f'Database query error: {str(e)}'}}), 500
    finally:
        cur.close()

    # ถ้าไม่พบข้อมูล
    if len(association) == 0:
        return jsonify({'response': {'status':'error','messege': 'data from DigitalOrdLotTB not found'}}), 404
    
    # select สมาคม #############################################################
    cur = mysql.connection.cursor()
    member = ""
    associationMem = []
    try:
        # วนลูปเพื่อใช้ id จาก dict ไป query ข้อมูลเพิ่มเติม
        for item in association:
            item_id = item["IDCard"]
            cur.execute(f"SELECT LotDate, Associate_mem_IDcard, Lotto_Nums FROM TaxAssociateMember WHERE LotDate={LotDate} AND Associate_IDcard = {item_id}")
            member = cur.fetchall()  # ดึงข้อมูลผลลัพธ์แถวแรก
            associationMem.extend(member)
    except Exception as e:
        return jsonify({'response': {'status':'error','messege': f'Database query error: {str(e)}'}}), 500
    finally:
        cur.close()

    # ถ้าไม่พบข้อมูล
    if len(associationMem) == 0:
        return jsonify({'response': {'status':'error','messege': 'data from TaxAssociateMember not found'}}), 404
    
    try:
        # รวม dict ของ สมาคมและทั่วไป เข้าด้วยกัน
        allAgent = []
        allAgent = list(generalMem) + associationMem
        new_list_of_allAgent = [{"IDCard": dict.get("IDCard", 0) or dict.get("Associate_mem_IDcard", 0), "Nums": dict.get("Nums", 0) or dict.get("Lotto_Nums", 0),"LotDate": dict.get("LotDate", 0), "Agent_Type": dict.get("Agent_Type", "สมาคม")} for dict in allAgent]
            
        # ปัดเศษเกินสมาคม เช่น nums=22 จะตัดlistให้เหลือ nums=20 และสร้างlistใหม่เป็นnums=2
        for dict in new_list_of_allAgent:
            remainder = dict["Nums"] % 5
            if (remainder != 0) and (dict["Nums"] >= 5):
                dict["Nums"] -= remainder
                new_dict = {"IDCard": dict["IDCard"],"Agent_Type": dict["Agent_Type"], "LotDate": dict["LotDate"], "Nums": remainder}
                new_list_of_allAgent.append(new_dict)

        # สลับลำดับของ tuples ใน list
        random.shuffle(new_list_of_allAgent)    
        # เรียงลำดับจากมากไปน้อยตามค่า "a"
        sorted_list = sorted(new_list_of_allAgent, key=lambda x: x["Nums"], reverse=True)
        
    except Exception as e:
        # ถ้าเกิดข้อผิดพลาด ให้ rollback
        mysql.connection.rollback()
        return jsonify({'response': {'status':'error','messege': f'Database query error: {str(e)}'}}), 500
    finally:
        cur.close() 
    
    # insert ข้อมูลที่จัดเตรียแล้ว ลง db prepareAgentInfo ###############################################
    cur = mysql.connection.cursor()
    try:
        # สร้างคำสั่ง SQL
        sql = "INSERT INTO prepareAgentInfo (LotDate, IDCard, Nums, Agent_Type) VALUES (%s, %s, %s, %s)"
        # ดึงค่าออกจาก dict แล้วใช้ executemany()
        values = [(item["LotDate"], item["IDCard"],item["Nums"], item["Agent_Type"]) for item in sorted_list]
        # Execute และ Commit
        cur.executemany(sql, values)
        mysql.connection.commit()                
    except Exception as e:
        # ถ้าเกิดข้อผิดพลาด ให้ rollback
        mysql.connection.rollback()
        return jsonify({'response': {'status':'error','messege': f'Database query error: {str(e)}'}}), 500
    finally:
        cur.close()        
        
    # select ข้อมูลเพื่อตรวจสอบว่าครบแล้วหรือไม่ ###################################################
    cur = mysql.connection.cursor()    
    try:
        cur.execute(f"select sum(Nums) from DigitalOrdLotTB WHERE LotDate={LotDate}")
        total_from_DigitalOrdLotTB = cur.fetchone()  # ถ้า None ให้เป็น 0        
        print(total_from_DigitalOrdLotTB)
        cur.execute(f"select sum(Nums) from prepareagentinfo WHERE LotDate={LotDate}")
        total_all_agent = cur.fetchone()  # ถ้า None ให้เป็น 0
        print(total_all_agent)
    except Exception as e:
        return jsonify({'response': {'status':'error','messege': f'Database query error: {str(e)}'}}), 500
    finally:
        cur.close()
        
    if total_all_agent != total_from_DigitalOrdLotTB :
        return jsonify({'response': {'status':'error','messege': 'การเตรียมข้อมูลใน prepareagentinfo table ไม่ตรงกับ DigitalOrdLotTB table'}}), 500
    
    # insert log ลง db transectionAgentAlocate ###################################################
    cur = mysql.connection.cursor()
    try:
        # สร้างคำสั่ง SQL
        end_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        print(end_datetime)
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO transectionagentalocate (LotDate, UserName, StartDateTime, EndDateTime, Actions) VALUES (%s, %s,%s, %s,%s)", (LotDate, userName, start_datetime, end_datetime, action))
        mysql.connection.commit()
        
    except Exception  as e:
        return jsonify({'response': {'status':'error','messege': f'Database query error: {str(e)}'}}), 500
    finally:
        cur.close()    
        
    return jsonify({'response': {'status':'success','messege':'success'}})
    

# @app.route("/agentAlocate", methods=["POST"])
# def Prepare_Agent_Info():   

# API เพื่อเพิ่มข้อมูลเข้าไปในตาราง users
# @app.route("/agent", methods=["POST"])
# def add_user():
#     # data = request.get_json()
#     # Associate_IDcard = data.get("Associate_IDcard")
#     # Associate_mem_IDcard = data.get("Associate_mem_IDcard")
#     # LotDate = data.get("LotDate")
#     # Lotto_Nums = data.get("Lotto_Nums")
    
#     data = request.get_json()
#     LotID = data.get("LotID")
#     LotDate = data.get("LotDate")
#     IDCard = data.get("IDCard")
#     FullName = data.get("FullName")
#     IDPhone = data.get("IDPhone")
#     Nums = data.get("Nums")
#     Agent_Type = data.get("Agent_Type")
#     Statuss = data.get("Statuss")

#     # if not name or not email:
#     #     return jsonify({"error": "Missing name or email"}), 400

#     # insert table
#     cur = mysql.connection.cursor()
#     cur.execute("INSERT INTO DigitalOrdLotTB (LotID, LotDate, IDCard, FullName, IDPhone, Nums, Agent_Type, Statuss) VALUES (%s, %s,%s, %s,%s, %s,%s, %s)", (LotID, LotDate, IDCard, FullName, IDPhone, Nums, Agent_Type, Statuss))
#     # cur.execute("INSERT INTO TaxAssociateMember (Associate_IDcard, Associate_mem_IDcard, LotDate, Lotto_Nums) VALUES (%s, %s,%s, %s)", (Associate_IDcard, Associate_mem_IDcard, LotDate, Lotto_Nums))
#     mysql.connection.commit()
#     cur.close()

#     return jsonify({"message": "User added successfully"}), 201

if __name__ == "__main__":
    app.run(debug=True)
