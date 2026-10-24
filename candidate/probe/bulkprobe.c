// macOS probe: time directory-walk strategies on a tree (warm cache), N threads.
// Strategies: 0 = getattrlistbulk minimal attrs (dumac set), 1 = getattrlistbulk wide attrs
// (+DEVID,MODTIME,FLAGS,LINKCOUNT,DATALENGTH,MOUNTSTATUS) with FSOPT 0x200, 2 = same without 0x200,
// 3 = readdir + fstatat, 4 = bulk minimal attrs, files only via bulk, but buffer 16 KB.
// Prints total allocated bytes, entries, and how many records lacked any requested attr.
#include <sys/attr.h>
#include <sys/stat.h>
#include <sys/vnode.h>
#include <dirent.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static int strat; static size_t bufsz = 128*1024;
typedef struct { int dirfd; } task;
static task *q; static atomic_long qh, qt; static long qcap = 1<<22;
static atomic_long pending, total, entries, missing;
static pthread_mutex_t mu = PTHREAD_MUTEX_INITIALIZER; static pthread_cond_t cv = PTHREAD_COND_INITIALIZER;
static long head, tail;
static void push(int fd){ pthread_mutex_lock(&mu); q[tail++ % qcap].dirfd=fd; atomic_fetch_add(&pending,1); pthread_cond_signal(&cv); pthread_mutex_unlock(&mu); }
static int pop(void){ pthread_mutex_lock(&mu); while(head==tail){ if(atomic_load(&pending)==0){pthread_cond_broadcast(&cv);pthread_mutex_unlock(&mu);return -1;} pthread_cond_wait(&cv,&mu);} int fd=q[head++ % qcap].dirfd; pthread_mutex_unlock(&mu); return fd; }
static void done(void){ if(atomic_fetch_sub(&pending,1)==1){pthread_mutex_lock(&mu);pthread_cond_broadcast(&cv);pthread_mutex_unlock(&mu);} }
static void subdir(int fd, const char *name){ int c=openat(fd,name,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC); if(c>=0) push(c); }
static void do_bulk(int fd, char *buf){
  struct attrlist al={0}; al.bitmapcount=ATTR_BIT_MAP_COUNT;
  int wide = strat==1||strat==2;
  al.commonattr=ATTR_CMN_RETURNED_ATTRS|ATTR_CMN_NAME|ATTR_CMN_ERROR|ATTR_CMN_OBJTYPE|ATTR_CMN_FILEID|(wide?(ATTR_CMN_DEVID|ATTR_CMN_MODTIME|ATTR_CMN_FLAGS):0);
  al.fileattr=ATTR_FILE_ALLOCSIZE|(wide?(ATTR_FILE_LINKCOUNT|ATTR_FILE_DATALENGTH):0);
  al.dirattr=wide?ATTR_DIR_MOUNTSTATUS:0;
  uint64_t opt = strat==1?0x200:0;
  for(;;){ int n=getattrlistbulk(fd,&al,buf,bufsz,opt); if(n<=0) break;
    char *p=buf; for(int i=0;i<n;i++){ uint32_t len=*(uint32_t*)p; char *f=p+4; attribute_set_t rs=*(attribute_set_t*)f; f+=sizeof rs;
      if((rs.commonattr&al.commonattr)!=al.commonattr) atomic_fetch_add(&missing,1);
      uint32_t err=0; if(rs.commonattr&ATTR_CMN_ERROR){err=*(uint32_t*)f;f+=4;}
      attrreference_t *nr=(attrreference_t*)f; char *name=(char*)f+nr->attr_dataoffset; f+=sizeof *nr;
      if(rs.commonattr&ATTR_CMN_DEVID) f+=4;
      uint32_t type=0; if(rs.commonattr&ATTR_CMN_OBJTYPE){type=*(uint32_t*)f;f+=4;}
      if(rs.commonattr&ATTR_CMN_MODTIME) f+=16;
      if(rs.commonattr&ATTR_CMN_FLAGS) f+=4;
      if(rs.commonattr&ATTR_CMN_FILEID) f+=8;
      if(rs.dirattr&ATTR_DIR_MOUNTSTATUS) f+=4;
      if(rs.fileattr&ATTR_FILE_LINKCOUNT) f+=4;
      int64_t alloc=0; if(rs.fileattr&ATTR_FILE_ALLOCSIZE){alloc=*(int64_t*)f;f+=8;}
      atomic_fetch_add(&entries,1);
      if(!err){ if(type==VDIR) subdir(fd,name); else atomic_fetch_add(&total,alloc); }
      p+=len; } }
}
static void do_readdir(int fd){
  int d=dup(fd); DIR *dp=fdopendir(d); struct dirent *e; struct stat st;
  while((e=readdir(dp))){ if(!strcmp(e->d_name,".")||!strcmp(e->d_name,"..")) continue; atomic_fetch_add(&entries,1);
    if(fstatat(fd,e->d_name,&st,AT_SYMLINK_NOFOLLOW)) continue;
    if(S_ISDIR(st.st_mode)) subdir(fd,e->d_name); else atomic_fetch_add(&total,st.st_blocks*512); }
  closedir(dp);
}
static void *worker(void *a){ char *buf=malloc(bufsz); int fd; while((fd=pop())>=0){ if(strat==3) do_readdir(fd); else do_bulk(fd,buf); close(fd); done(); } free(buf); return 0; }
static double now(void){ struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec/1e9; }
int main(int c, char **v){
  if(c<4){fprintf(stderr,"usage: bulkprobe strategy threads path [bufKB]\n");return 2;}
  strat=atoi(v[1]); int nt=atoi(v[2]); if(c>4) bufsz=atoi(v[4])*1024; if(strat==4){strat=0; bufsz=16*1024;}
  q=malloc(sizeof(task)*qcap); double t0=now();
  push(open(v[3],O_RDONLY|O_DIRECTORY));
  pthread_t th[64]; for(int i=0;i<nt;i++) pthread_create(&th[i],0,worker,0); for(int i=0;i<nt;i++) pthread_join(th[i],0);
  printf("%.1f ms total=%ld entries=%ld missing=%ld\n",(now()-t0)*1e3,(long)total,(long)entries,(long)missing); return 0;
}
