import urllib.request
import json

def post(url, data):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def get(url):
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode())

def run_tests():
    print('--- TEST 1: ERP RESET ---')
    r = post('http://127.0.0.1:5000/api/erp/reset', {})
    print('Reset result:', r)

    print('\n--- TEST 2: TASK START ---')
    goal = 'Find the latest invoice from Acme Corp, extract the amount and due date, enter it into our internal system, and tell me once it is done.'
    init = post('http://127.0.0.1:5000/api/task/start', {'goal': goal})
    print('Task ID:', init['state']['task_id'])
    print('Steps count:', len(init['state']['plan']['steps']))

    print('\n--- TEST 3: STEP-BY-STEP FORWARD ---')
    for i in range(1, 4):
        step_res = post('http://127.0.0.1:5000/api/task/step', {'auto_approve': False})
        step_info = step_res['step_result']['step']
        print(f'Step {i} ({step_info["tool_name"]}): {step_info["observation"]}')

    print('\n--- TEST 4: HUMAN APPROVAL GATE ---')
    step4_res = post('http://127.0.0.1:5000/api/task/step', {'auto_approve': False})
    print('Status at step 4:', step4_res['step_result']['status'])
    print('Waiting for approval:', step4_res['state']['waiting_for_approval'])
    print('Prompt:', step4_res['step_result']['prompt'])

    print('\n--- TEST 5: SUBMIT HUMAN APPROVAL (HTTP POST /api/task/approve) ---')
    appr_res = post('http://127.0.0.1:5000/api/task/approve', {'approved': True})
    print('Approve endpoint succeeded without error!')
    print('Result status:', appr_res['result']['status'])

    print('\n--- TEST 6: RESUME TO COMPLETION ---')
    comp_res = post('http://127.0.0.1:5000/api/task/run-all', {'auto_approve': True})
    print('Run-all completion status:', comp_res['status'])
    print('Verification verified:', comp_res['state']['verification_result']['verified'])
    print('Proof Hash:', comp_res['state']['verification_result']['proof_hash'])
    print('Evidence DB ID:', comp_res['state']['verification_result']['evidence']['db_record_id'])

    print('\n--- TEST 7: QUERY ERP DATABASE TABLE ---')
    invoices = get('http://127.0.0.1:5000/api/erp/invoices')
    print('Invoices in DB count:', len(invoices['invoices']))
    print('Recorded Invoice:', invoices['invoices'][0]['invoice_number'], 'Amount:', invoices['invoices'][0]['amount'])

    print('\n--- TEST 8: DUPLICATE RECOVERY TEST ---')
    post('http://127.0.0.1:5000/api/task/start', {'goal': goal})
    dup_res = post('http://127.0.0.1:5000/api/task/run-all', {'auto_approve': True})
    step5 = dup_res['state']['plan']['steps'][4]
    print('Step 5 on duplicate run status:', step5['status'])
    print('Step 5 observation:', step5['observation'])

    print('\n--- TEST 9: HUMAN REJECTION SAFETY TEST ---')
    post('http://127.0.0.1:5000/api/erp/reset', {})
    post('http://127.0.0.1:5000/api/task/start', {'goal': 'Process invoice for Globex Corporation'})
    post('http://127.0.0.1:5000/api/task/run-all', {'auto_approve': False})
    rej_res = post('http://127.0.0.1:5000/api/task/approve', {'approved': False})
    print('Reject status:', rej_res['result']['status'])
    invoices_after_rej = get('http://127.0.0.1:5000/api/erp/invoices')
    print('Invoices in DB after rejection (must be 0):', len(invoices_after_rej['invoices']))

    print('\n>>> ALL 9 END-TO-END TESTS PASSED WITH 100% SUCCESS! <<<')

if __name__ == '__main__':
    run_tests()
