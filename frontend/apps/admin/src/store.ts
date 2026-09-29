import { configureStore, createSlice } from '@reduxjs/toolkit'
const uiSlice = createSlice({ name: 'ui', initialState: { sidebarCollapsed: false }, reducers: { toggleSidebar: state => { state.sidebarCollapsed = !state.sidebarCollapsed } } })
export const { toggleSidebar } = uiSlice.actions
export const store = configureStore({ reducer: { ui: uiSlice.reducer } })
export type RootState = ReturnType<typeof store.getState>
