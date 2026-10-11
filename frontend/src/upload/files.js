export function csvFile(files) {
  if (files.length !== 1) throw new Error('CSV 파일을 하나만 선택해 주세요.');
  const file = files[0];
  if (!file.name.toLowerCase().endsWith('.csv')) throw new Error('CSV 파일을 선택해 주세요.');
  if (!file.size || file.size > 10 * 1024 * 1024) throw new Error('파일은 0바이트보다 크고 10MB 이하여야 합니다.');
  return file;
}
