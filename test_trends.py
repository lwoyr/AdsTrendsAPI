"""Google Trends APIの改善されたレート制限処理をテストするスクリプト。"""
import asyncio
import time
from trends import trends_manager

async def test_bulk_trends():
    """大量のキーワードでテストして429エラー処理を確認。"""
    # 200個のテストキーワードを生成
    test_keywords = [f"python {i}" for i in range(200)]
    
    print(f"テスト開始: {len(test_keywords)}個のキーワード")
    start_time = time.time()
    
    results = await trends_manager.get_bulk_trends(test_keywords)
    
    # 結果の統計
    successful = sum(1 for v in results.values() if v is not None)
    failed = sum(1 for v in results.values() if v is None)
    
    elapsed_time = time.time() - start_time
    
    print(f"\nテスト結果:")
    print(f"- 成功: {successful}/{len(test_keywords)} ({successful/len(test_keywords)*100:.1f}%)")
    print(f"- 失敗: {failed}/{len(test_keywords)} ({failed/len(test_keywords)*100:.1f}%)")
    print(f"- 実行時間: {elapsed_time:.1f}秒")
    
    # サンプル結果を表示
    print("\nサンプル結果（最初の10件）:")
    for i, (keyword, score) in enumerate(list(results.items())[:10]):
        if score is not None:
            print(f"  {keyword}: {score:.1f}")
        else:
            print(f"  {keyword}: 失敗")
    
    return successful, failed

if __name__ == "__main__":
    asyncio.run(test_bulk_trends())