# ------------------------------------------------------------------------------
# This file is part of Appy, a framework for building applications in the Python
# language. Copyright (C) 2007 Gaetan Delannay

# Appy is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation; either version 3 of the License, or (at your option) any later
# version.

# Appy is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.

# You should have received a copy of the GNU General Public License along with
# Appy. If not, see <http://www.gnu.org/licenses/>.
# ------------------------------------------------------------------------------
import types, string
from appy.gen.mail import sendNotification

# Default Appy permissions -----------------------------------------------------
r, w, d = ('read', 'write', 'delete')

# ------------------------------------------------------------------------------
class Role:
    '''Represents a role, be it local or global.'''
    zopeRoles = ('Manager', 'Owner', 'Anonymous', 'Authenticated')
    zopeLocalRoles = ('Owner',)
    zopeUngrantableRoles = ('Anonymous', 'Authenticated')
    def __init__(self, name, local=False, grantable=True):
        self.name = name
        self.local = local # True if it can be used as local role only.
        # It is a standard Zope role or an application-specific one?
        self.zope = name in self.zopeRoles
        if self.zope and (name in self.zopeLocalRoles):
            self.local = True
        self.grantable = grantable
        if self.zope and (name in self.zopeUngrantableRoles):
            self.grantable = False
        # An ungrantable role is one that is, like the Anonymous or
        # Authenticated roles, automatically attributed to a user.

# ------------------------------------------------------------------------------
class State:
    '''Represents a workflow state.'''
    def __init__(self, permissions, initial=False, phase=None, show=True):
        self.usedRoles = {}
        # The following dict ~{s_permissionName:[s_roleName|Role_role]}~
        # gives, for every permission managed by a workflow, the list of roles
        # for which the permission is granted in this state. Standard
        # permissions are 'read', 'write' and 'delete'.
        self.permissions = permissions 
        self.initial = initial
        self.phase = phase
        self.show = show
        # Standardize the way roles are expressed within self.permissions
        self.standardizeRoles()

    def getName(self, wf):
        '''Returns the name for this state in workflow p_wf.'''
        for name in dir(wf):
            value = getattr(wf, name)
            if (value == self): return name

    def getRole(self, role):
        '''p_role can be the name of a role or a Role instance. If it is the
           name of a role, this method returns self.usedRoles[role] if it
           exists, or creates a Role instance, puts it in self.usedRoles and
           returns it else. If it is a Role instance, the method stores it in
           self.usedRoles if it is not in it yet and returns it.'''
        if isinstance(role, basestring):
            if role in self.usedRoles:
                return self.usedRoles[role]
            else:
                theRole = Role(role)
                self.usedRoles[role] = theRole
                return theRole
        else:
            if role.name not in self.usedRoles:
                self.usedRoles[role.name] = role
            return role

    def standardizeRoles(self):
        '''This method converts, within self.permissions, every role to a
           Role instance. Every used role is stored in self.usedRoles.'''
        for permission, roles in self.permissions.items():
            if isinstance(roles, basestring) or isinstance(roles, Role):
                self.permissions[permission] = [self.getRole(roles)]
            elif roles:
                rolesList = []
                for role in roles:
                    rolesList.append(self.getRole(role))
                self.permissions[permission] = rolesList

    def getUsedRoles(self): return self.usedRoles.values()

# ------------------------------------------------------------------------------
class Transition:
    '''Represents a workflow transition.'''
    def __init__(self, states, condition=True, action=None, notify=None,
                 show=True, confirm=False):
        self.states = states # In its simpler form, it is a tuple with 2
        # states: (fromState, toState). But it can also be a tuple of several
        # (fromState, toState) sub-tuples. This way, you may define only 1
        # transition at several places in the state-transition diagram. It may
        # be useful for "undo" transitions, for example.
        self.condition = condition
        if isinstance(condition, basestring):
            # The condition specifies the name of a role.
            self.condition = Role(condition)
        self.action = action
        self.notify = notify # If not None, it is a method telling who must be
        # notified by email after the transition has been executed.
        self.show = show # If False, the end user will not be able to trigger
        # the transition. It will only be possible by code.
        self.confirm = confirm # If True, a confirm popup will show up.

    def getName(self, wf):
        '''Returns the name for this state in workflow p_wf.'''
        for name in dir(wf):
            value = getattr(wf, name)
            if (value == self): return name

    def getUsedRoles(self):
        '''self.condition can specify a role.'''
        res = []
        if isinstance(self.condition, Role):
            res.append(self.condition)
        return res

    def isSingle(self):
        '''If this transition is only defined between 2 states, returns True.
           Else, returns False.'''
        return isinstance(self.states[0], State)

    def isShowable(self, workflow, obj):
        '''Is this transition showable?'''
        if callable(self.show):
            return self.show(workflow, obj.appy())
        else:
            return self.show

    def hasState(self, state, isFrom):
        '''If p_isFrom is True, this method returns True if p_state is a
           starting state for p_self. If p_isFrom is False, this method returns
           True if p_state is an ending state for p_self.'''
        stateIndex = 1
        if isFrom:
            stateIndex = 0
        if self.isSingle():
            res = state == self.states[stateIndex]
        else:
            res = False
            for states in self.states:
                if states[stateIndex] == state:
                    res = True
                    break
        return res

    def isTriggerable(self, obj, wf, noSecurity=False):
        '''Can this transition be triggered on p_obj?'''
        wf = wf.__instance__ # We need the prototypical instance here.
        # Checks that the current state of the object is a start state for this
        # transition.
        objState = obj.State(name=False)
        if self.isSingle():
            if objState != self.states[0]: return False
        else:
            startFound = False
            for startState, stopState in self.states:
                if startState == objState:
                    startFound = True
                    break
            if not startFound: return False
        # Check that the condition is met, excepted if noSecurity is True.
        if noSecurity: return True
        user = obj.getTool().getUser()
        if isinstance(self.condition, Role):
            # Condition is a role. Transition may be triggered if the user has
            # this role.
            return user.has_role(self.condition.name, obj)
        elif type(self.condition) == types.FunctionType:
            return self.condition(wf, obj.appy())
        elif type(self.condition) in (tuple, list):
            # It is a list of roles and/or functions. Transition may be
            # triggered if user has at least one of those roles and if all
            # functions return True.
            hasRole = None
            for condition in self.condition:
                # "Unwrap" role names from Role instances.
                if isinstance(condition, Role): condition = condition.name
                if isinstance(condition, basestring): # It is a role
                    if hasRole == None:
                        hasRole = False
                    if user.has_role(condition, obj):
                        hasRole = True
                else: # It is a method
                    if not condition(wf, obj.appy()):
                        return False
            if hasRole != False:
                return True

    def executeAction(self, obj, wf):
        '''Executes the action related to this transition.'''
        msg = ''
        obj = obj.appy()
        wf = wf.__instance__ # We need the prototypical instance here.
        if type(self.action) in (tuple, list):
            # We need to execute a list of actions
            for act in self.action:
                msgPart = act(wf, obj)
                if msgPart: msg += msgPart
        else: # We execute a single action only.
            msgPart = self.action(wf, obj)
            if msgPart: msg += msgPart
        return msg

    def trigger(self, transitionName, obj, wf, comment, doAction=True,
                doNotify=True, doHistory=True, doSay=True):
        '''This method triggers this transition on p_obj. The transition is
           supposed to be triggerable (call to self.isTriggerable must have been
           performed before calling this method). If p_doAction is False, the
           action that must normally be executed after the transition has been
           triggered will not be executed. If p_doNotify is False, the
           email notifications that must normally be launched after the
           transition has been triggered will not be launched. If p_doHistory is
           False, there will be no trace from this transition triggering in the
           workflow history. If p_doSay is False, we consider the transition is
           trigger programmatically, and no message is returned to the user.'''
        # Create the workflow_history dict if it does not exist.
        if not hasattr(obj.aq_base, 'workflow_history'):
            from persistent.mapping import PersistentMapping
            obj.workflow_history = PersistentMapping()
        # Create the event list if it does not exist in the dict
        if not obj.workflow_history: obj.workflow_history['appy'] = ()
        # Get the key where object history is stored (this overstructure is
        # only there for backward compatibility reasons)
        key = obj.workflow_history.keys()[0]
        # Identify the target state for this transition
        if self.isSingle():
            targetState = self.states[1]
            targetStateName = targetState.getName(wf)
        else:
            startState = obj.State(name=False)
            for sState, tState in self.states:
                if startState == sState:
                    targetState = tState
                    targetStateName = targetState.getName(wf)
                    break
        # Create the event and add it in the object history
        action = transitionName
        if transitionName == '_init_': action = None
        if not doHistory: comment = '_invisible_'
        obj.addHistoryEvent(action, review_state=targetStateName,
                            comments=comment)
        # Reindex the object if required. Not only security-related indexes
        # (Allowed, State) need to be updated here.
        if not obj.isTemporary(): obj.reindex()
        # Execute the related action if needed
        msg = ''
        if doAction and self.action: msg = self.executeAction(obj, wf)
        # Send notifications if needed
        if doNotify and self.notify and obj.getTool(True).mailEnabled:
            sendNotification(obj.appy(), self, transitionName, wf)
        # Return a message to the user if needed
        if not doSay or (transitionName == '_init_'): return
        if not msg: msg = obj.translate('object_saved')
        obj.say(msg)

# ------------------------------------------------------------------------------
class Permission:
    '''If you need to define a specific read or write permission for some field
       on a gen-class, you use the specific boolean attrs
       "specificReadPermission" or "specificWritePermission". When you want to
       refer to those specific read or write permissions when
       defining a workflow, for example, you need to use instances of
       "ReadPermission" and "WritePermission", the 2 children classes of this
       class. For example, if you need to refer to write permission of
       attribute "t1" of class A, write: WritePermission("A.t1") or
       WritePermission("x.y.A.t1") if class A is not in the same module as
       where you instantiate the class.

       Note that this holds only if you use attributes "specificReadPermission"
       and "specificWritePermission" as booleans. When defining named
       (string) permissions, for referring to it you simply use those strings,
       you do not create instances of ReadPermission or WritePermission.'''

    allowedChars = string.digits + string.letters + '_'

    def __init__(self, fieldDescriptor):
        self.fieldDescriptor = fieldDescriptor

    def getName(self, wf, appName):
        '''Returns the name of this permission.'''
        className, fieldName = self.fieldDescriptor.rsplit('.', 1)
        if className.find('.') == -1:
            # The related class resides in the same module as the workflow
            fullClassName= '%s_%s' % (wf.__module__.replace('.', '_'),className)
        else:
            # className contains the full package name of the class
            fullClassName = className.replace('.', '_')
        # Read or Write ?
        if self.__class__.__name__ == 'ReadPermission': access = 'Read'
        else: access = 'Write'
        return '%s: %s %s %s' % (appName, access, fullClassName, fieldName)

class ReadPermission(Permission): pass
class WritePermission(Permission): pass

# Standard workflows -----------------------------------------------------------
class WorkflowAnonymous:
    '''One-state workflow allowing anyone to consult and Manager to edit.'''
    mgr = 'Manager'
    o = 'Owner'
    active = State({r:(mgr, 'Anonymous', 'Authenticated'), w:(mgr,o),d:(mgr,o)},
                   initial=True)

class WorkflowAuthenticated:
    '''One-state workflow allowing authenticated users to consult and Manager
       to edit.'''
    mgr = 'Manager'
    o = 'Owner'
    active = State({r:(mgr, 'Authenticated'), w:(mgr,o), d:(mgr,o)},
                   initial=True)

class WorkflowOwner:
    '''One-state workflow allowing only manager and owner to consult and
       edit.'''
    mgr = 'Manager'
    o = 'Owner'
    active = State({r:(mgr, o), w:(mgr, o), d:mgr}, initial=True)
# ------------------------------------------------------------------------------