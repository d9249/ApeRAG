"""
그래프 API 테스트 스크립트
"""

import requests
import json
import time

# API 서버 주소
BASE_URL = "http://localhost:8001"

def test_text_input():
    """텍스트 직접 입력 테스트"""
    print("📝 텍스트 직접 입력으로 그래프 생성 테스트")
    
    # 샘플 텍스트 (한국의 주요 기업들)
    sample_text = """
    삼성전자는 대한민국의 대표적인 전자 기업입니다. 이재용 부회장이 경영진을 이끌고 있으며, 
    스마트폰, 반도체, 디스플레이 등을 제조합니다. 수원에 본사가 있고 전 세계에 지사를 두고 있습니다.
    
    LG전자는 또 다른 한국의 주요 전자 기업입니다. 가전제품, 스마트폰, 디스플레이 기술 분야에서 
    활동하고 있습니다. 서울 여의도에 본사가 위치하고 있습니다.
    
    SK하이닉스는 메모리 반도체 전문 기업입니다. 이천과 청주에 주요 공장을 운영하고 있으며, 
    DRAM과 NAND 플래시 메모리를 생산합니다.
    
    현대자동차그룹은 자동차 제조 기업으로, 현대자동차와 기아자동차를 포함합니다. 
    정의선 회장이 그룹을 이끌고 있으며, 전기차와 수소차 개발에 투자하고 있습니다.
    """
    
    try:
        response = requests.post(
            f"{BASE_URL}/create_from_text",
            json={
                "content": sample_text,
                "doc_id": "korean_companies",
                "file_path": "korean_companies.txt"
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 텍스트 입력 성공!")
            print(f"   문서 ID: {result['document_id']}")
            print(f"   청크 생성: {result['graph_result']['chunks_created']}개")
            print(f"   엔티티 추출: {result['graph_result']['entities_extracted']}개")
            print(f"   관계 추출: {result['graph_result']['relations_extracted']}개")
            return result['document_id']
        else:
            print(f"❌ 텍스트 입력 실패: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        return None


def test_graph_labels(document_id):
    """그래프 라벨 조회 테스트"""
    print(f"\n🏷️  문서 '{document_id}'의 그래프 라벨 조회")
    
    try:
        response = requests.get(f"{BASE_URL}/documents/{document_id}/labels")
        
        if response.status_code == 200:
            result = response.json()
            labels = result['data']['labels']
            print(f"✅ 라벨 조회 성공! ({len(labels)}개)")
            print("   라벨들:", labels[:10])  # 처음 10개만 표시
            return labels
        else:
            print(f"❌ 라벨 조회 실패: {response.status_code}")
            print(response.text)
            return []
            
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        return []


def test_knowledge_graph(document_id, node_label):
    """지식 그래프 조회 테스트"""
    print(f"\n🔗 '{node_label}' 중심의 지식 그래프 조회")
    
    try:
        response = requests.post(
            f"{BASE_URL}/documents/{document_id}/knowledge_graph",
            json={
                "node_label": node_label,
                "max_depth": 2,
                "max_nodes": 50
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            kg = result['data']['knowledge_graph']
            print(f"✅ 지식 그래프 조회 성공!")
            print(f"   노드 수: {kg['node_count']}개")
            print(f"   엣지 수: {kg['edge_count']}개")
            return kg
        else:
            print(f"❌ 지식 그래프 조회 실패: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        return None


def test_query(document_id, query_text):
    """질의 응답 테스트"""
    print(f"\n❓ 질의: '{query_text}'")
    
    try:
        response = requests.post(
            f"{BASE_URL}/documents/{document_id}/query",
            json={
                "query": query_text,
                "mode": "hybrid"
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            answer = result['data']['answer']
            print(f"✅ 답변 받음!")
            print(f"   답변: {answer}")
            return answer
        else:
            print(f"❌ 질의 실패: {response.status_code}")
            print(response.text)
            return None
            
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        return None


def test_document_list():
    """문서 목록 조회 테스트"""
    print(f"\n📋 문서 목록 조회")
    
    try:
        response = requests.get(f"{BASE_URL}/documents")
        
        if response.status_code == 200:
            result = response.json()
            documents = result['data']['documents']
            print(f"✅ 문서 목록 조회 성공! ({len(documents)}개)")
            for doc in documents:
                print(f"   - {doc['document_id']}: {doc['filename']} (그래프: {doc['graph_created']})")
            return documents
        else:
            print(f"❌ 문서 목록 조회 실패: {response.status_code}")
            print(response.text)
            return []
            
    except Exception as e:
        print(f"❌ 오류 발생: {str(e)}")
        return []


def main():
    """메인 테스트 함수"""
    print("🚀 그래프 API 테스트 시작")
    print("=" * 50)
    
    # 1. 텍스트 입력으로 그래프 생성
    document_id = test_text_input()
    if not document_id:
        print("❌ 텍스트 입력 단계에서 실패했습니다.")
        return
    
    # 잠시 대기 (그래프 생성 완료 대기)
    print("\n⏳ 그래프 생성 완료 대기 중... (3초)")
    time.sleep(3)
    
    # 2. 그래프 라벨 조회
    labels = test_graph_labels(document_id)
    
    # 3. 지식 그래프 조회 (첫 번째 라벨 사용)
    if labels:
        test_knowledge_graph(document_id, labels[0])
    
    # 4. 질의 응답 테스트
    test_queries = [
        "삼성전자의 본사는 어디에 있나요?",
        "현대자동차그룹의 회장은 누구인가요?",
        "메모리 반도체를 생산하는 회사는 어디인가요?"
    ]
    
    for query in test_queries:
        test_query(document_id, query)
    
    # 5. 문서 목록 조회
    test_document_list()
    
    print("\n🎉 테스트 완료!")


if __name__ == "__main__":
    main()