from typing import Protocol
from sqlalchemy import select
from app.database.store import SessionLocal,CustomerDemoProfile

class CoreBankingAdapter(Protocol):
    def get_customer(self,customer_id:str)->dict:...
    def get_accounts(self,customer_id:str)->list[dict]:...
    def get_balance(self,customer_id:str)->dict:...
    def get_transactions(self,customer_id:str)->list[dict]:...
    def get_card_status(self,customer_id:str)->list[dict]:...
    def get_transfer_status(self,customer_id:str)->list[dict]:...
    def get_loan_details(self,customer_id:str)->list[dict]:...
    def get_deposit_details(self,customer_id:str)->list[dict]:...

SEEDS=[('CSB10001','Maya Rao (Demo)','blue',24850),('CSB10002','Arun Shah (Demo)','green',41720),('CSB10003','Leena Das (Demo)','purple',18600)]

def seed_customers()->None:
    with SessionLocal() as db:
        for i,(cid,name,color,balance) in enumerate(SEEDS):
            if db.get(CustomerDemoProfile,cid):continue
            data={'id':cid,'name':name,'synthetic':True,'caller_alias':'DEMO-CALLER-'+str(i+1),'challenge':'What is the favourite colour shown on this fictional demo profile?','demo_answer':color,
                'accounts':[{'id':f'DEMO-SAV-{i+1}','type':'Savings','masked_number':'DEMO-****-'+str(1001+i),'available_balance':balance,'ledger_balance':balance+1150,'currency':'INR','status':'ACTIVE'}],
                'transactions':[{'id':f'DEMO-TX-{i+1}-{j+1}','date':f'2026-09-{24-j:02}','merchant':merchant,'amount':amount,'direction':direction,'status':status,'channel':channel} for j,(merchant,amount,direction,status,channel) in enumerate([('Sample Groceries',850,'DEBIT','COMPLETED','UPI'),('Demo Salary',32000,'CREDIT','COMPLETED','NEFT'),('Example Transit',120,'DEBIT','COMPLETED','CARD'),('Fictional Utilities',1500,'DEBIT','PENDING','UPI'),('Sample Bookshop',640,'DEBIT','COMPLETED','CARD')])],
                'cards':[{'id':f'DEMO-CARD-{i+1}','masked_number':'DEMO-****-'+str(4001+i),'type':'DEBIT','status':'ACTIVE','expiry':'2027-10','online_enabled':True,'international_enabled':False},
                         {'id':f'DEMO-CREDIT-{i+1}','masked_number':'DEMO-****-'+str(5001+i),'type':'CREDIT','status':'ACTIVE','limit':75000,'available_limit':63000,'total_due':12000,'minimum_due':600,'due_date':'2026-10-05'}],
                'transfers':[{'reference':f'DEMO-NEFT-{i+1}','channel':'NEFT','amount':5000,'status':'PENDING','date':'2026-09-23','beneficiary':'Example Recipient'}],
                'loans':[{'id':f'DEMO-LOAN-{i+1}','type':'Personal','outstanding':125000,'emi':5800,'next_due':'2026-10-07','status':'CURRENT','rate_percent':12}],
                'deposits':[{'id':f'DEMO-FD-{i+1}','type':'Fixed deposit','principal':50000,'rate_percent':6,'maturity':'2027-03-10','instruction':'Credit proceeds to demo savings'}],
                'kyc_status':'COMPLETE','notification_preferences':{'email':True,'sms':True}}
            db.add(CustomerDemoProfile(id=cid,data=data))
        db.commit()

class MockCoreBankingAdapter:
    def get_customer(self,customer_id:str)->dict:
        with SessionLocal() as db:
            item=db.get(CustomerDemoProfile,customer_id)
            if not item:raise ValueError('Synthetic customer not found')
            return item.data
    def list_customers(self)->list[dict]:
        with SessionLocal() as db:return [x.data for x in db.scalars(select(CustomerDemoProfile))]
    def get_accounts(self,cid):return self.get_customer(cid)['accounts']
    def get_balance(self,cid):return self.get_accounts(cid)[0]
    def get_transactions(self,cid):return self.get_customer(cid)['transactions']
    def get_card_status(self,cid):return self.get_customer(cid)['cards']
    def get_transfer_status(self,cid):return self.get_customer(cid)['transfers']
    def get_loan_details(self,cid):return self.get_customer(cid)['loans']
    def get_deposit_details(self,cid):return self.get_customer(cid)['deposits']
    def block_demo_card(self,cid:str)->dict:
        with SessionLocal() as db:
            row=db.get(CustomerDemoProfile,cid)
            if not row:raise ValueError('Synthetic customer not found')
            data={**row.data,'cards':[dict(c) for c in row.data['cards']]}
            data['cards'][0]['status']='BLOCKED'
            row.data=data;db.commit()
            return {'synthetic':True,'card':data['cards'][0],'message':'Only the synthetic demo card has been blocked. No real card was changed.'}
    def evidence(self,cid:str,intent:str)->dict|None:
        p=self.get_customer(cid); text=None
        if intent=='account_balance_information':
            a=p['accounts'][0];text=f"Synthetic demo account: available balance INR {a['available_balance']:,.2f}; ledger balance INR {a['ledger_balance']:,.2f}. This is fictional data for {p['name']}, not a real bank account."
        elif intent in {'transaction_history','statement_download'}:
            entries='; '.join(f"{t['date']}: {t['merchant']}, INR {t['amount']:,.2f}, {t['direction'].lower()}, {t['status'].lower()}" for t in p['transactions'][:5])
            text='The latest five synthetic transactions are '+entries+'. These are fictional demo records.'
        elif intent in {'card_status','card_block'}:
            text='The synthetic debit card '+p['cards'][0]['masked_number']+' is '+p['cards'][0]['status'].lower()+'. This status applies only to the demo record.'
        elif intent in {'credit_limit','credit_dues','credit_billing'}:
            c=p['cards'][1];text=f"Your synthetic credit-card limit is INR {c['limit']:,.2f}, with INR {c['available_limit']:,.2f} available. The fictional total due is INR {c['total_due']:,.2f}, minimum due INR {c['minimum_due']:,.2f}, and due date {c['due_date']}. These are demo figures only."
        elif intent in {'loan_status','loan_payment','loan_closure'}:
            l=p['loans'][0];text=f"The synthetic loan outstanding principal is INR {l['outstanding']:,.2f}. Its configured EMI is INR {l['emi']:,.2f}, next due on {l['next_due']}, with status {l['status'].lower()}. This is not a real settlement quote."
        elif intent in {'deposit_status','fd_maturity'}:
            d=p['deposits'][0];text=f"The synthetic fixed deposit has principal INR {d['principal']:,.2f} and a configured annual rate of {d['rate_percent']} percent. Its demo maturity date is {d['maturity']}; the instruction is {d['instruction'].lower()}. These are fictional product records."
        elif intent=='transaction_status':
            t=p['transfers'][0];text=f"The synthetic {t['channel']} transfer {t['reference']} for INR {t['amount']:,.2f} is {t['status'].lower()}. This is a fictional record and does not indicate the status of any real transfer."
        if not text:return None
        customer_text=self.customer_evidence(p,intent)
        return {'customer_content':customer_text,'id':f'DEMO-{cid}-{intent}','title':'Verified synthetic core record','content':text,'source_type':'DEMO_ACCOUNT_INFORMATION','category':'demo_core','supported_intents':[intent],'intent_match':True,'score':1.0,'similarity':1.0,'filename':'synthetic-core-adapter','approved':True}

    def customer_evidence(self,p,intent):
        if intent=='account_balance_information':
            a=p['accounts'][0]
            return f"Your available balance is INR {a['available_balance']:,.2f}. Your ledger balance is INR {a['ledger_balance']:,.2f}."
        if intent in {'transaction_history','statement_download'}:
            def merchant(name):
                import re
                return re.sub(r'\b(?:demo|fictional|synthetic)\s*','',name,flags=re.I).strip()
            return 'Your latest five transactions are '+ '; '.join(f"{t['date']}: {merchant(t['merchant'])}, INR {t['amount']:,.2f}, {t['direction'].lower()}, {t['status'].lower()}" for t in p['transactions'][:5])+'.'
        if intent in {'card_status','card_block'}:
            c=p['cards'][0]
            return f"The debit card ending {c['masked_number'][-4:]} has a status of {c['status'].lower()} in the account record. For changes to your card, please use the verified banking channel."
        if intent in {'credit_limit','credit_dues','credit_billing'}:
            c=p['cards'][1]
            return f"Your credit-card limit is INR {c['limit']:,.2f}, with INR {c['available_limit']:,.2f} available. Your total due is INR {c['total_due']:,.2f}, minimum due INR {c['minimum_due']:,.2f}, and due date {c['due_date']}."
        if intent in {'loan_status','loan_payment','loan_closure'}:
            l=p['loans'][0]
            return f"Your outstanding principal is INR {l['outstanding']:,.2f}. Your EMI is INR {l['emi']:,.2f}, next due on {l['next_due']}. Please request a settlement quote before closing the loan."
        if intent in {'deposit_status','fd_maturity'}:
            d=p['deposits'][0]
            return f"Your fixed deposit principal is INR {d['principal']:,.2f}. The recorded annual rate is {d['rate_percent']} percent, with maturity on {d['maturity']}."
        if intent=='transaction_status':
            t=p['transfers'][0]
            return f"The {t['channel']} transfer for INR {t['amount']:,.2f} is marked {t['status'].lower()} in the account record."
        return ''

core_banking=MockCoreBankingAdapter()
