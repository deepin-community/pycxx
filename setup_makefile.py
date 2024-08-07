#
#   Copyright (c) 2010-2011 Barry A. Scott
#
import os
import sys
import sysconfig
import subprocess

_debug = False

def debug( msg ):
    if _debug:
        sys.stderr.write( 'Debug: %s\n' % (msg,) )

#--------------------------------------------------------------------------------
class Setup:
    def __init__( self, argv ):
        global _debug

        args = iter(argv)
        next(args)

        self.opt_pycxx_debug = False
        self.opt_limited_api = None
        self.opt_warnings_as_errors = False
        self.opt_cpp_std = None
        self.opt_cc_std = None

        self.is_pypy = hasattr( sys, 'pypy_version_info' )

        positional_args = []

        for arg in args:
            if arg == '--debug':
                _debug = True

            elif arg == '--pycxx-debug':
                self.opt_pycxx_debug = True

            elif arg == '--limited-api':
                self.opt_limited_api = '0x03040000'

            elif arg.startswith( '--limited-api=' ):
                api = arg[len('--limited-api='):]
                if api.startswith( '0x' ):
                    self.opt_limited_api = api
                else:
                    major, minor = [int(s) for s in api.split('.')]
                    minor *= 0x10000
                    major *= 0x1000000
                    self.opt_limited_api = '0x%x' % (major+minor)

            elif arg.startswith( '--c++-std=' ):
                self.opt_cpp_std = arg[len('--c++-std='):]

            elif arg.startswith( '--c-std=' ):
                self.opt_cc_std = arg[len('--c-std='):]

            elif arg == '--warnings-as-errors':
                self.opt_warnings_as_errors = True

            elif arg.startswith( '--' ):
                raise ValueError( 'Unknown arg %r' % (arg,) )

            else:
                positional_args.append( arg )

        if len(positional_args) != 2:
            raise ValueError( 'Usage: setup_makefile.py win32|win64|macosx|linux> <makefile>' )

        self.platform, makefile = positional_args

        self.__makefile = open( makefile, 'wt' )

        self.setupCompile()

    def makePrint( self, line ):
        self.__makefile.write( line )
        self.__makefile.write( '\n' )

    def setupCompile( self ):
        if self.platform == 'win32':
            self.c_utils = Win32CompilerMSVC90( self )
            self.c_python_extension = Win32CompilerMSVC90( self )

        elif self.platform == 'win64':
            self.c_utils = Win32CompilerMSVC90( self )
            self.c_python_extension = Win32CompilerMSVC90( self )

        elif self.platform == 'macosx':
            self.c_utils = MacOsxCompilerGCC( self )
            self.c_python_extension = MacOsxCompilerGCC( self )

        elif self.platform == 'linux':
            self.c_utils = LinuxCompilerGCC( self )
            self.c_python_extension = LinuxCompilerGCC( self )

        else:
            raise ValueError( 'Unknown platform %r' % (self.platform,) )

        self.c_python_extension.setupPythonExtension()

        self.pycxx_obj_file = [
            Source( self.c_python_extension, 'Src/cxxsupport.cxx' ),
            Source( self.c_python_extension, 'Src/cxx_extensions.cxx' ),
            Source( self.c_python_extension, 'Src/cxx_exceptions.cxx' ),
            Source( self.c_python_extension, 'Src/cxxextensions.c' ),
            Source( self.c_python_extension, 'Src/IndirectPythonInterface.cxx' ),
            ]

        self.simple_obj_files = [
            Source( self.c_python_extension, '%(DEMO_DIR)s/simple.cxx' ),
            ] + self.pycxx_obj_file

        self.example_obj_files = [
            Source( self.c_python_extension, '%(DEMO_DIR)s/example.cxx' ),
            Source( self.c_python_extension, '%(DEMO_DIR)s/range.cxx' ),
            Source( self.c_python_extension, '%(DEMO_DIR)s/rangetest.cxx' ),
            ] + self.pycxx_obj_file

        self.pycxx_iter_obj_files = [
            Source( self.c_python_extension, '%(DEMO_DIR)s/pycxx_iter.cxx' ),
            ] + self.pycxx_obj_file


        exe_simple = PythonExtension( self.c_python_extension, 'simple', self.simple_obj_files )
        exe_example = PythonExtension( self.c_python_extension, 'example', self.example_obj_files )
        exe_pycxx_iter = PythonExtension( self.c_python_extension, 'pycxx_iter', self.pycxx_iter_obj_files )

        self.all_exe = [
            exe_simple,
            exe_example,
            exe_pycxx_iter,
            ]

        self.all_test = [
            TestPythonExtension( self.c_python_extension, '%(DEMO_DIR)s/test_simple.py', exe_simple ),
            TestPythonExtension( self.c_python_extension, '%(DEMO_DIR)s/test_example.py', exe_example ),
            TestPythonExtension( self.c_python_extension, '%(DEMO_DIR)s/test_pycxx_iter.py', exe_pycxx_iter ),
            ]

    def generateMakefile( self ):
        try:
            self.c_python_extension.generateMakefileHeader()

            self.makePrint( 'all: %s' % (' '.join( [exe.getTargetFilename() for exe in self.all_exe] )) )
            self.makePrint( '' )

            for exe in self.all_exe:
                exe.generateMakefile()

            for test in self.all_test:
                test.generateMakefile()

            self.__makefile.close()

            return 0

        except ValueError:
            e = sys.exc_info()[1]
            sys.stderr.write( 'Error: %s\n' % (e,) )
            return 1

#--------------------------------------------------------------------------------
class Compiler:
    def __init__( self, setup ):
        debug( 'Compiler.__init__()' )
        self.setup = setup

        self.__variables = {}

        self._addVar( 'DEBUG',           'NDEBUG')

    def platformFilename( self, filename ):
        return filename

    def makePrint( self, line ):
        self.setup.makePrint( line )

    def generateMakefileHeader( self ):
        raise NotImplementedError( 'generateMakefileHeader' )

    def _addFromEnv( self, name ):
        debug( 'Compiler._addFromEnv( %r )' % (name,) )

        self._addVar( name, os.environ[ name ] )

    def _addVar( self, name, value ):
        debug( 'Compiler._addVar( %r, %r )' % (name, value) )

        try:
            if '%' in value:
                value = value % self.__variables

            self.__variables[ name ] = value

        except TypeError:
            raise ValueError( 'Cannot translate name %r value %r' % (name, value) )

        except KeyError:
            e = sys.exc_info()[1]
            raise ValueError( 'Cannot translate name %r value %r - %s' % (name, value, e) )

    def expand( self, s ):
        try:
            return s % self.__variables

        except (TypeError, KeyError):
            e = sys.exc_info()[1]

            print( 'Error: %s' % (e,) )
            print( 'String: %s' % (s,) )
            print( 'Vairables: %r' % (self.__variables,) )

            raise ValueError( 'Cannot translate string (%s)' % (e,) )


# MSVC 9.0 and later versions
class Win32CompilerMSVC90(Compiler):
    def __init__( self, setup ):
        Compiler.__init__( self, setup )

        self._addVar( 'PYTHONDIR',      sys.exec_prefix )
        if setup.opt_limited_api is None:
            self._addVar( 'PYTHON_LIBNAME', 'python%d%d' % (sys.version_info[0], sys.version_info[1]) )
        else:
            self._addVar( 'PYTHON_LIBNAME', 'python3' )
        self._addVar( 'PYTHON_INCLUDE', r'%(PYTHONDIR)s\include' )
        self._addVar( 'PYTHON_LIB',     r'%(PYTHONDIR)s\libs' )
        self._addVar( 'PYTHON',         sys.executable )

    def platformFilename( self, filename ):
        return filename.replace( '/', '\\' )

    def getPythonExtensionFileExt( self ):
        return '.pyd'

    def getProgramExt( self ):
        return '.exe'

    def generateMakefileHeader( self ):
        self.makePrint( '#' )
        self.makePrint( '#	PyCXX Makefile generated by setup_makefile.py' )
        self.makePrint( '#' )
        self.makePrint( 'CCC=cl /nologo /W4' )
        self.makePrint( 'CC=cl /nologo /W4' )
        self.makePrint( '' )
        self.makePrint( 'LDSHARED=$(CCC) /LD /Zi /MT /EHsc' )
        self.makePrint( 'LDEXE=$(CCC) /Zi /MT /EHsc' )
        self.makePrint( '' )

    def ruleLinkProgram( self, target ):
        pyd_filename = target.getTargetFilename()
        pdf_filename = target.getTargetFilename( '.pdf' )

        all_objects = [source.getTargetFilename() for source in target.all_sources]

        rules = ['']

        rules.append( '' )
        rules.append( '%s : %s' % (pyd_filename, ' '.join( all_objects )) )
        rules.append( '\t@echo Link %s' % (pyd_filename,) )
        rules.append( '\t$(LDEXE)  %%(CCCFLAGS)s /Fe%s /Fd%s %s Advapi32.lib' %
                            (pyd_filename, pdf_filename, ' '.join( all_objects )) )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

    def ruleLinkShared( self, target ):
        pyd_filename = target.getTargetFilename()
        pdf_filename = target.getTargetFilename( '.pdf' )

        all_objects = [source.getTargetFilename() for source in target.all_sources]

        rules = ['']

        rules.append( '' )
        rules.append( '%s : %s' % (pyd_filename, ' '.join( all_objects )) )
        rules.append( '\t@echo Link %s' % (pyd_filename,) )
        rules.append( '\t$(LDSHARED)  %%(CCCFLAGS)s /Fe%s /Fd%s %s %%(PYTHON_LIB)s\%%(PYTHON_LIBNAME)s.lib' %
                            (pyd_filename, pdf_filename, ' '.join( all_objects )) )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

    def ruleCxx( self, target ):
        obj_filename = target.getTargetFilename()

        rules = []

        rules.append( '%s: %s %s' % (obj_filename, target.src_filename, ' '.join( target.all_dependencies )) )
        rules.append( '\t@echo Compile: %s into %s' % (target.src_filename, target.getTargetFilename()) )
        rules.append( '\t$(CCC) /c %%(CCCFLAGS)s /Fo%s /Fd%s %s' % (obj_filename, target.dependent.getTargetFilename( '.pdb' ), target.src_filename) )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

    def ruleC( self, target ):
        obj_filename = target.getTargetFilename()

        rules = []

        rules.append( '%s: %s %s' % (obj_filename, target.src_filename, ' '.join( target.all_dependencies )) )
        rules.append( '\t@echo Compile: %s into %s' % (target.src_filename, target.getTargetFilename()) )
        rules.append( '\t$(CC) /c %%(CCFLAGS)s /Fo%s /Fd%s %s' % (obj_filename, target.dependent.getTargetFilename( '.pdb' ), target.src_filename) )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

    def ruleClean( self, filename ):
        rules = []
        rules.append( 'clean::' )
        rules.append( '\tif exist %s del %s' % (filename, filename) )
        rules.append( '' )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

    def setupPythonExtension( self ):
        self._addVar( 'PYTHON',         sys.executable )

        self._addVar( 'OBJ_DIR',        'obj' )

        self._addVar( 'PYTHON_VERSION', '%d.%d' % (sys.version_info[0], sys.version_info[1]) )

        self._addVar( 'DEMO_DIR',       'Demo\Python%d' % (sys.version_info[0],) )

        self._addVar( 'PYCXX_DEBUG',    '-DPYCXX_DEBUG=1' if self.setup.opt_pycxx_debug else '' )
        self._addVar( 'PYCXX_API',      ('-DPy_LIMITED_API=%s' % (self.setup.opt_limited_api,)) if self.setup.opt_limited_api else '' )

        self._addVar( 'CCCFLAGS',
                                        r'/Zi /MT /EHsc '
                                        r'-I. -ISrc -I%(PYTHON_INCLUDE)s '
                                        r'-D_CRT_NONSTDC_NO_DEPRECATE '
                                        r'-U_DEBUG '
                                        r'-D%(DEBUG)s '
                                        r'%(PYCXX_DEBUG)s'
                                        r'%(PYCXX_API)s' )

        self._addVar( 'CCFLAGS',
                                        r'/Zi /MT '
                                        r'-I. -ISrc -I%(PYTHON_INCLUDE)s '
                                        r'-D_CRT_NONSTDC_NO_DEPRECATE '
                                        r'-U_DEBUG '
                                        r'-D%(DEBUG)s '
                                        r'%(PYCXX_DEBUG)s'
                                        r'%(PYCXX_API)s' )

    def ruleTest( self, python_test ):
        rules = []
        rules.append( 'test:: %s %s' % (python_test.getTargetFilename(), python_test.python_extension.getTargetFilename()) )
        rules.append( '\tset PYTHONPATH=obj' )
        rules.append( '\t%%(PYTHON)s -W default %s' % (python_test.getTargetFilename(),) )
        rules.append( '' )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

class CompilerGCC(Compiler):
    def __init__( self, setup ):
        Compiler.__init__( self, setup )

    def getPythonExtensionFileExt( self ):
        return '.so'

    def getProgramExt( self ):
        return ''

    def generateMakefileHeader( self ):
        self.makePrint( '#' )
        self.makePrint( '#	PyCXX Makefile generated by setup_makefile.py' )
        self.makePrint( '#' )
        self.makePrint( '' )

    def ruleLinkProgram( self, target ):
        target_filename = target.getTargetFilename()

        all_objects = [source.getTargetFilename() for source in target.all_sources]

        rules = []

        rules.append( '%s : %s' % (target_filename, ' '.join( all_objects )) )
        rules.append( '\t@echo Link %s' % (target_filename,) )
        rules.append( '\t%%(LDEXE)s -o %s %%(CCFLAGS)s %s' % (target_filename, ' '.join( all_objects )) )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

    def ruleLinkShared( self, target ):
        target_filename = target.getTargetFilename()

        all_objects = [source.getTargetFilename() for source in target.all_sources]

        rules = []

        rules.append( '%s : %s' % (target_filename, ' '.join( all_objects )) )
        rules.append( '\t@echo Link %s' % (target_filename,) )
        rules.append( '\t%%(LDSHARED)s -o %s %%(CCFLAGS)s %s' % (target_filename, ' '.join( all_objects )) )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

    def ruleCxx( self, target ):
        obj_filename = target.getTargetFilename()

        rules = []

        rules.append( '%s: %s %s' % (obj_filename, target.src_filename, ' '.join( target.all_dependencies )) )
        rules.append( '\t@echo Compile: %s into %s' % (target.src_filename, obj_filename) )
        rules.append( '\t%%(CCC)s -c %%(CCCFLAGS)s -o%s  %s' % (obj_filename, target.src_filename) )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

    def ruleC( self, target ):
        obj_filename = target.getTargetFilename()

        rules = []

        rules.append( '%s: %s %s' % (obj_filename, target.src_filename, ' '.join( target.all_dependencies )) )
        rules.append( '\t@echo Compile: %s into %s' % (target.src_filename, obj_filename) )
        rules.append( '\t%%(CC)s -c %%(CCCFLAGS)s -o%s  %s' % (obj_filename, target.src_filename) )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

    def ruleClean( self, filename ):
        rules = []
        rules.append( 'clean::' )
        rules.append( '\trm -f %s' % (filename,) )
        rules.append( '' )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

    def ruleTest( self, python_test ):
        rules = []
        rules.append( 'test:: %s %s' % (python_test.getTargetFilename(), python_test.python_extension.getTargetFilename()) )
        rules.append( '\tPYTHONPATH=obj %%(PYTHON)s -W default %s' % (python_test.getTargetFilename(),) )
        rules.append( '' )

        self.makePrint( self.expand( '\n'.join( rules ) ) )

class MacOsxCompilerGCC(CompilerGCC):
    def __init__( self, setup ):
        CompilerGCC.__init__( self, setup )
        if sys.version_info[0] == 2:
            maxsize = sys.maxint
        else:
            maxsize = sys.maxsize

        r = subprocess.run( ['lipo', '-archs', sys.executable], capture_output=True )
        all_archs = r.stdout.decode('utf-8').strip().split()

        self._addVar( 'CCC',            'g++ %s' % (' '.join('-arch %s' % (a,) for a in all_archs),) )
        self._addVar( 'CC',             'gcc %s' % (' '.join('-arch %s' % (a,) for a in all_archs),) )

    def setupPythonExtension( self ):
        self._addVar( 'PYTHON',         sys.executable )

        self._addVar( 'OBJ_DIR',       'obj' )

        self._addVar( 'PYTHON_VERSION', '%d.%d' % (sys.version_info[0], sys.version_info[1]) )

        self._addVar( 'PYTHONDIR',      sys.exec_prefix )

        self._addVar( 'PYTHON',         sys.executable )

        if self.setup.is_pypy:
            self._addVar( 'PYTHON_INCLUDE', '%(PYTHONDIR)s/include' )
            self._addVar( 'PYTHON_FRAMEWORK', '%(PYTHONDIR)s/bin/libpypy-c.dylib' )

        else:
            self._addVar( 'PYTHON_INCLUDE', '%(PYTHONDIR)s/Headers' )
            self._addVar( 'PYTHON_FRAMEWORK', '%(PYTHONDIR)s/Python' )

        self._addVar( 'DEMO_DIR',       'Demo/Python%d' % (sys.version_info[0],) )

        self._addVar( 'PYCXX_DEBUG',    '-DPYCXX_DEBUG=1' if self.setup.opt_pycxx_debug else '' )
        self._addVar( 'PYCXX_API',      ('-DPy_LIMITED_API=%s' % (self.setup.opt_limited_api,)) if self.setup.opt_limited_api else '' )

        self._addVar( 'WARN_AS_ERROR',  '-Werror' if self.setup.opt_warnings_as_errors else '' )
        self._addVar( 'CPP_STD',        '-std=%s' % (self.setup.opt_cpp_std,) if self.setup.opt_cpp_std is not None else '' )
        self._addVar( 'CC_STD',         '-std=%s' % (self.setup.opt_cc_std,) if self.setup.opt_cc_std is not None else '' )

        self._addVar( 'CCCFLAGS',
                                        '-g '
                                        '-Wall -fPIC -fexceptions -frtti '
                                        '-I. -ISrc -I%(PYTHON_INCLUDE)s '
                                        '-D%(DEBUG)s '
                                        '%(WARN_AS_ERROR)s '
                                        '%(CPP_STD)s '
                                        '%(PYCXX_DEBUG)s'
                                        '%(PYCXX_API)s' )
        self._addVar( 'CCFLAGS',
                                        '-g '
                                        '-Wall -fPIC '
                                        '-I. -ISrc -I%(PYTHON_INCLUDE)s '
                                        '-D%(DEBUG)s '
                                        '-Werror '
                                        '%(PYCXX_DEBUG)s'
                                        '%(PYCXX_API)s' )

        self._addVar( 'CCCFLAGS',
                                        '-g '
                                        '-Wall -fPIC -fexceptions -frtti '
                                        '-I. -ISrc -I%(PYTHON_INCLUDE)s '
                                        '-D%(DEBUG)s '
                                        '%(WARN_AS_ERROR)s '
                                        '%(CPP_STD)s '
                                        '%(PYCXX_DEBUG)s'
                                        '%(PYCXX_API)s' )

        self._addVar( 'CCFLAGS',
                                        '-g '
                                        '-Wall -fPIC '
                                        '-I. -ISrc -I%(PYTHON_INCLUDE)s '
                                        '-D%(DEBUG)s '
                                        '%(WARN_AS_ERROR)s '
                                        '%(CC_STD)s '
                                        '%(PYCXX_DEBUG)s'
                                        '%(PYCXX_API)s' )

        self._addVar( 'LDSHARED',       '%(CCC)s -bundle -g '
                                        '-framework System '
                                        '%(PYTHON_FRAMEWORK)s ' )

class LinuxCompilerGCC(CompilerGCC):
    def __init__( self, setup ):
        CompilerGCC.__init__( self, setup )
        self._addVar( 'CCC',            'g++' )
        self._addVar( 'CC',             'gcc' )

    def setupPythonExtension( self ):
        self._addVar( 'PYTHON',         sys.executable )

        self._addVar( 'OBJ_DIR',       'obj' )

        self._addVar( 'DEMO_DIR',       'Demo/Python%d' % (sys.version_info[0],) )

        self._addVar( 'PYTHON_VERSION', '%d.%d' % (sys.version_info[0], sys.version_info[1]) )
        self._addVar( 'PYTHON_INCLUDE', sysconfig.get_path( 'include' ) )
        self._addVar( 'PYCXX_DEBUG',    '-DPYCXX_DEBUG=1' if self.setup.opt_pycxx_debug else '' )
        self._addVar( 'PYCXX_API',      ('-DPy_LIMITED_API=%s' % (self.setup.opt_limited_api,)) if self.setup.opt_limited_api else '' )

        self._addVar( 'WARN_AS_ERROR',  '-Werror' if self.setup.opt_warnings_as_errors else '' )
        self._addVar( 'CPP_STD',        '-std=%s' % (self.setup.opt_cpp_std,) if self.setup.opt_cpp_std is not None else '' )
        self._addVar( 'CC_STD',         '-std=%s' % (self.setup.opt_cc_std,) if self.setup.opt_cc_std is not None else '' )

        self._addVar( 'CCCFLAGS',
                                        '-g '
                                        '-Wall -fPIC -fexceptions -frtti '
                                        '-I. -ISrc -I%(PYTHON_INCLUDE)s '
                                        '-D%(DEBUG)s '
                                        '%(WARN_AS_ERROR)s '
                                        '%(CPP_STD)s '
                                        '%(PYCXX_DEBUG)s '
                                        '%(PYCXX_API)s ' )
        self._addVar( 'CCFLAGS',
                                        '-g '
                                        '-Wall -fPIC '
                                        '-I. -ISrc -I%(PYTHON_INCLUDE)s '
                                        '-D%(DEBUG)s '
                                        '%(WARN_AS_ERROR)s '
                                        '%(CC_STD)s '
                                        '%(PYCXX_DEBUG)s'
                                        '%(PYCXX_API)s' )

        self._addVar( 'LDEXE',          '%(CCC)s -g' )
        self._addVar( 'LDSHARED',       '%(CCC)s -shared -g ' )


#--------------------------------------------------------------------------------
class Target:
    def __init__( self, compiler, all_sources ):
        self.compiler = compiler
        self.__generated = False
        self.dependent = None


        self.all_sources = all_sources
        for source in self.all_sources:
            source.setDependent( self )

    def getTargetFilename( self ):
        raise NotImplementedError( '%s.getTargetFilename' % self.__class__.__name__ )

    def generateMakefile( self ):
        if self.__generated:
            return

        self.__generated = True
        return self._generateMakefile()

    def _generateMakefile( self ):
        raise NotImplementedError( '_generateMakefile' )

    def ruleClean( self, ext=None ):
        if ext is None:
            target_filename = self.getTargetFilename()
        else:
            target_filename = self.getTargetFilename( ext )

        self.compiler.ruleClean( target_filename )

    def setDependent( self, dependent ):
        debug( '%r.setDependent( %r )' % (self, dependent,) )
        self.dependent = dependent

class TestPythonExtension(Target):
    def __init__( self, compiler, test_source, python_extension ):
        self.test_source = test_source
        self.python_extension = python_extension

        Target.__init__( self, compiler, [] )

    def __repr__( self ):
        return '<TestPythonExtension:0x%8.8x %s>' % (id(self), self.test_source )

    def getTargetFilename( self ):
        return self.compiler.platformFilename( self.compiler.expand( self.test_source ) )

    def _generateMakefile( self ):
        self.compiler.ruleTest( self )

class PythonExtension(Target):
    def __init__( self, compiler, output, all_sources ):
        self.output = output

        Target.__init__( self, compiler, all_sources )
        debug( 'PythonExtension:0x%8.8x.__init__( %r, ... )' % (id(self), output,) )

        for source in self.all_sources:
            source.setDependent( self )

    def __repr__( self ):
        return '<PythonExtension:0x%8.8x %s>' % (id(self), self.output)

    def getTargetFilename( self, ext=None ):
        if ext is None:
            ext = self.compiler.getPythonExtensionFileExt()
        return self.compiler.platformFilename( self.compiler.expand( '%%(OBJ_DIR)s/%s%s' % (self.output, ext) ) )

    def _generateMakefile( self ):
        debug( 'PythonExtension:0x%8.8x.generateMakefile() for %r' % (id(self), self.output,) )

        self.compiler.ruleLinkShared( self )
        self.compiler.ruleClean( self.getTargetFilename( '.*' ) )

        for source in self.all_sources:
            source.generateMakefile()

class Source(Target):
    def __init__( self, compiler, src_filename, all_dependencies=None ):
        self.src_filename = compiler.platformFilename( compiler.expand( src_filename ) )

        Target.__init__( self, compiler, [] )

        debug( 'Source:0x%8.8x.__init__( %r, %r )' % (id(self), src_filename, all_dependencies) )

        self.all_dependencies = all_dependencies
        if self.all_dependencies is None:
            self.all_dependencies = []

    def __repr__( self ):
        return '<Source:0x%8.8x %s>' % (id(self), self.src_filename)

    def getTargetFilename( self ):
        #if not os.path.exists( self.src_filename ):
        #    raise ValueError( 'Cannot find source %s' % (self.src_filename,) )

        basename = os.path.basename( self.src_filename )
        if basename.endswith( '.cpp' ):
            return self.compiler.platformFilename( self.compiler.expand( r'%%(OBJ_DIR)s/%s.obj' % (basename[:-len('.cpp')],) ) )

        if basename.endswith( '.cxx' ):
            return self.compiler.platformFilename( self.compiler.expand( r'%%(OBJ_DIR)s/%s.obj' % (basename[:-len('.cxx')],) ) )

        if basename.endswith( '.c' ):
            return self.compiler.platformFilename( self.compiler.expand( r'%%(OBJ_DIR)s/%s.obj' % (basename[:-len('.c')],) ) )

        raise ValueError( 'unknown source %r' % (self.src_filename,) )

    def _generateMakefile( self ):
        debug( 'Source:0x%8.8x.generateMakefile() for %r' % (id(self), self.src_filename,) )

        if self.src_filename.endswith( '.c' ):
            self.compiler.ruleC( self )

        else:
            self.compiler.ruleCxx( self )

        self.compiler.ruleClean( self.getTargetFilename() )

#--------------------------------------------------------------------------------
def main( argv ):
    try:
        s = Setup( argv )
        s.generateMakefile()
        return 0

    except ValueError:
        e = sys.exc_info()[1]
        sys.stderr.write( 'Error: %s\n' % (e,) )
        return 1

if __name__ == '__main__':
    sys.exit( main( sys.argv ) )
