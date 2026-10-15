"""Versioned, authored domain corpus. No runtime scenario switches."""
import json
from pathlib import Path
from functools import lru_cache

DOMAIN = Path(__file__).resolve().parents[1] / 'domain'
KB = Path(__file__).resolve().parents[1] / 'knowledge_base'
@lru_cache
def topics() -> list[dict]:
    return [row for p in sorted(DOMAIN.glob('*.json')) if p.name != 'products.json' for row in json.loads(p.read_text(encoding='utf-8-sig'))]

@lru_cache
def products() -> dict:
    return json.loads((DOMAIN/'products.json').read_text(encoding='utf-8-sig'))

def examples(topic: dict) -> list[str]:
    # Multiple styles; held-out evaluation does not reuse these question templates.
    a = topic['aliases']
    templates = ['How does {x} work?', 'I need help with {x}.', 'Could you explain {x} to me?',
                 'Please tell me about {x}.', 'Hi, I am calling about {x}.', 'Need some info on {x}, please.']
    return [pattern.format(x=alias) for alias in a[:3] for pattern in templates]

def seed_articles() -> list[dict]:
    articles = []
    for t in topics():
        for suffix,body,kind in [('concept',t['overview'],'GENERAL_BANKING_INFORMATION'),('procedure',t['procedure'],'BANK_POLICY')]:
            articles.append({'id':f"KB-{t['id']}-{suffix}",'title':t['title']+(' - explained' if suffix=='concept' else ' - support procedure'),
                'category':t['category'],'subcategory':t['id'],'supported_intents':[t['id']],'intent':t['id'],
                'risk_level':t['risk'],'authentication_required':False,'last_reviewed':'2026-09-24',
                'source_type':kind,'keywords':t['aliases'],'aliases':t['aliases'],'content':body,'customer_content':t.get('customer_'+suffix,body),
                'enabled':True,'approved':True,'seed_version':2,'filename':f"{t['category']}/{t['id']}_{suffix}.json"})
    p = products()
    structured = [
        ('rates','Configured synthetic deposit and loan rates',['interest_rate_information','fixed_deposit','fd_maturity','recurring_deposit','loan_interest'],
         f"Call Sense Bank's fictional annual rates are {p['rates']['savings_annual_percent']} percent for demo savings, {p['rates']['fd_12_month_annual_percent']} percent for a 12-month demo fixed deposit, {p['rates']['rd_12_month_annual_percent']} percent for a 12-month demo recurring deposit, and {p['rates']['personal_loan_annual_percent']} percent for the example personal loan. These are synthetic configuration values, not market offers. A different tenure or product needs its own configured quote."),
        ('fees','Configured synthetic service fees',['account_fees','card_fees','service_fee_schedule','transfer_limits_reference'],
         f"The fictional fee schedule lists INR {p['fees']['savings_monthly_service']} for monthly demo savings service, INR {p['fees']['debit_annual']} for annual debit-card service, INR {p['fees']['debit_replacement']} for debit-card replacement, INR {p['fees']['neft_online']} for online NEFT, INR {p['fees']['cheque_book_25_leaves']} for a 25-leaf cheque book, and INR {p['fees']['loan_late_installment']} for the example loan late-installment charge. No other fee or tax is implied."),
        ('limits','Configured synthetic transaction limits',['card_controls','atm_limits_charges','transfer_limits_reference','upi_mandates'],
         f"The demo debit card has a daily ATM limit of INR {p['limits']['demo_debit_daily_atm']} and a daily online spending limit of INR {p['limits']['demo_card_online_daily']}. The fictional bank-transfer limit is INR {p['limits']['demo_transfer_daily']} per day. These are simulation settings, not regulatory limits. A UPI-specific limit is not configured and must not be inferred from the transfer limit.")]
    for key,title,intents,body in structured:
        articles.append({'id':'KB-PRODUCT-'+key,'title':title,'category':'product_configuration','subcategory':key,
                         'supported_intents':intents,'intent':','.join(intents),'risk_level':'LOW','authentication_required':False,
                         'last_reviewed':'2026-09-24','source_type':'BANK_POLICY','keywords':[key,'rate','fee','limit'],
                         'aliases':[],'content':body,'enabled':True,'approved':True,'seed_version':2,'filename':f'product_configuration/{key}.json'})
    return articles

def export_knowledge_files() -> None:
    for article in seed_articles():
        p = KB/article['filename']
        p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists():
            p.write_text(json.dumps(article,indent=2),encoding='utf-8')

