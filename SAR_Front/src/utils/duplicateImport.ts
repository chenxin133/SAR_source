import { h } from 'vue'
import { ElButton, ElMessageBox } from 'element-plus'
import { HttpError } from '../services/http'

export type DuplicateAction = 'ask' | 'reuse' | 'import' | 'update'
export class ImportCancelledError extends Error {
  constructor() { super('已取消导入') }
}

export const chooseDuplicate = (existing: { id: string; name: string }): Promise<DuplicateAction> =>
  new Promise((resolve, reject) => {
    const choose = (action: DuplicateAction) => { resolve(action); ElMessageBox.close() }
    void ElMessageBox({
      title: '文件已存在', showConfirmButton: false, showCancelButton: false,
      closeOnClickModal: false, type: 'warning',
      message: h('div', [
        h('p', `相同内容已存在：${existing.name}（${existing.id}）`),
        h('p', '使用原本记录保留原有信息；作为副本导入会新增记录；更新信息导入会保留 ID 和关联，更新本次填写的信息。'),
        h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap;margin-top:16px' }, [
          h(ElButton, { type: 'primary', onClick: () => choose('reuse') }, () => '使用原本记录'),
          h(ElButton, { onClick: () => choose('import') }, () => '作为副本导入'),
          h(ElButton, { onClick: () => choose('update') }, () => '更新信息导入'),
          h(ElButton, { onClick: () => { reject(new ImportCancelledError()); ElMessageBox.close() } }, () => '取消')
        ])
      ])
    }).catch(() => reject(new ImportCancelledError()))
  })

export const withDuplicateChoice = async <T>(operation: (action: DuplicateAction) => Promise<T>): Promise<T> => {
  try {
    return await operation('ask')
  } catch (error) {
    const detail = error instanceof HttpError ? error.detail as any : undefined
    if (error instanceof HttpError && error.status === 409 && detail?.code === 'duplicate_file' && detail.existing) {
      return operation(await chooseDuplicate(detail.existing))
    }
    throw error
  }
}
