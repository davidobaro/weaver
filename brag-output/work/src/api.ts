export class ApiError extends Error { constructor(message:string, public noteId?:number){super(message)} }
export async function api<T>(path:string,method='GET',body?:unknown):Promise<T>{return new Promise(()=>{})}
